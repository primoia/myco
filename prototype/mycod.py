#!/usr/bin/env python3
"""
mycod - myco daemon, phase 0 prototype

Watches log/*.log files in a swarm directory, maintains an in-memory state
index, and regenerates view/*.md files atomically whenever state changes.

Stateless: if the daemon restarts, it reindexes from the logs.
No persistence beyond the filesystem.

Usage:
    mycod.py <swarm_dir>

The swarm directory must contain:
    log/    - per-session append-only logs (one file per session)
    view/   - per-session curated views (written by daemon)

Protocol v0. See docs/PROTOCOL.md for the event format.
"""

import os
import sys
import time
import tempfile
from collections import defaultdict, deque
from pathlib import Path


# ---------- Event parsing ----------

def parse_event(session: str, line: str):
    """Parse a log line into an event dict. Returns None if malformed."""
    line = line.strip()
    if not line:
        return None
    parts = line.split(None, 4)
    if len(parts) < 3:
        return None
    ts = parts[0]
    # parts[1] is the session id declared in the line; we trust filename
    verb = parts[2] if len(parts) > 2 else ""
    obj = parts[3] if len(parts) > 3 else ""
    detail = parts[4] if len(parts) > 4 else ""
    return {
        "ts": ts,
        "session": session,
        "verb": verb,
        "obj": obj,
        "detail": detail,
        "raw": line,
    }


# ---------- In-memory index ----------

class SwarmIndex:
    def __init__(self):
        self.session_status = {}
        self.session_action = {}
        self.needs = defaultdict(set)
        self.provides = defaultdict(set)
        self.resources = {}
        self.directives = []
        self.questions = []
        self.events = deque(maxlen=2000)
        self.sessions_known = set()

    def apply(self, ev):
        s = ev["session"]
        self.sessions_known.add(s)
        self.events.append(ev)

        verb = ev["verb"]
        obj = ev["obj"]
        detail = ev["detail"]

        # Resource names can be multi-token: "up container iam-db"
        # We concatenate obj + detail for resource verbs
        full_obj = f"{obj} {detail}".strip() if detail else obj

        if verb == "start":
            self.session_status[s] = "active"
            self.session_action[s] = f"start {obj}"
        elif verb == "done":
            self.session_status[s] = "idle"
            self.session_action[s] = f"done {obj}"
            artifact = f"{s}.{obj}"
            self.provides[s].add(artifact)
            self.provides[s].add(obj)
        elif verb == "need":
            self.needs[s].add(obj)
        elif verb == "block":
            self.session_status[s] = "blocked"
            self.session_action[s] = f"blocked: {obj} {detail}".strip()
        elif verb == "up":
            self.resources[full_obj] = "UP"
        elif verb == "down":
            self.resources[full_obj] = "DOWN"
        elif verb == "direct":
            self.directives.append((ev["ts"], obj, detail))
        elif verb == "ask":
            self.questions.append((ev["ts"], s, obj, detail))
        elif verb == "note":
            # note events update last-seen but don't change semantic state
            if s not in self.session_status:
                self.session_status[s] = "idle"
                self.session_action[s] = f"note {obj}"

    def satisfied(self, artifact: str) -> bool:
        for provided in self.provides.values():
            if artifact in provided:
                return True
        return False

    def blockers_for(self, session: str):
        return [n for n in self.needs.get(session, set()) if not self.satisfied(n)]

    def dependents_of(self, session: str):
        deps = []
        my_provides = self.provides.get(session, set())
        for other, other_needs in self.needs.items():
            if other == session:
                continue
            if other_needs & my_provides:
                deps.append(other)
        return deps

    def recent_events_for(self, session: str, limit=15):
        # DIRECTOR is the observer: it sees all semantic events
        if session == "DIRECTOR":
            relevant = [
                ev for ev in reversed(self.events)
                if ev["verb"] != "note"
            ]
            return list(reversed(relevant[:limit]))

        relevant = []
        my_needs = self.needs.get(session, set())
        my_provides = self.provides.get(session, set())

        # Sessions that provide things we need
        upstream = set()
        for other, other_provides in self.provides.items():
            if other_provides & my_needs:
                upstream.add(other)

        for ev in reversed(self.events):
            s = ev["session"]
            obj = ev["obj"]
            verb = ev["verb"]

            # Skip note spam from other sessions
            if verb == "note" and s != session:
                continue

            # directives are always relevant
            if verb == "direct":
                relevant.append(ev)
            # own events
            elif s == session:
                relevant.append(ev)
            # events from upstream sessions
            elif s in upstream:
                relevant.append(ev)
            # events that mention something we provide
            elif obj in my_provides or f"{s}.{obj}" in my_provides:
                relevant.append(ev)
            # questions addressed to us
            elif verb == "ask" and obj == session:
                relevant.append(ev)

            if len(relevant) >= limit:
                break
        return list(reversed(relevant[:limit]))


# ---------- Rendering ----------

def render_view(index: SwarmIndex, session: str) -> str:
    blockers = index.blockers_for(session)
    dependents = index.dependents_of(session)
    resources = dict(index.resources)
    directives = list(index.directives)
    events = index.recent_events_for(session, limit=15)
    status = index.session_status.get(session, "unknown")
    action = index.session_action.get(session, "no recent action")
    my_questions = [q for q in index.questions if q[1] == session or q[2] == session]

    lines = []
    lines.append("<!-- myco protocol v0 -->")
    lines.append(f"# myco view — {session}")
    lines.append("")
    lines.append("## AGORA")
    if session == "DIRECTOR":
        workers = sorted(s for s in index.sessions_known if s != "DIRECTOR")
        lines.append(f"Swarm com {len(workers)} sessões worker ativas.")
        if workers:
            lines.append("")
            lines.append("| sessão | status | última ação |")
            lines.append("|---|---|---|")
            for s in workers:
                st = index.session_status.get(s, "unknown")
                ac = index.session_action.get(s, "—")
                lines.append(f"| {s} | {st} | {ac} |")
    else:
        lines.append(f"Status: **{status}** — {action}")
        if blockers:
            lines.append(f"Bloqueado por: {', '.join(blockers)}")
        else:
            if status != "blocked":
                lines.append("Nenhum bloqueador conhecido.")
    lines.append("")

    lines.append("## DIRETIVAS")
    relevant_directives = [
        (ts, t, txt) for ts, t, txt in directives
        if t in ("all", session)
    ]
    if relevant_directives:
        for ts, target, text in relevant_directives[-5:]:
            lines.append(f"- [{ts}] {text}")
    else:
        lines.append("Nenhuma diretiva ativa.")
    lines.append("")

    if session != "DIRECTOR":
        lines.append("## SEUS BLOQUEADORES")
        if blockers:
            for b in blockers:
                lines.append(f"- {b}")
        else:
            lines.append("Nenhum.")
        lines.append("")

        lines.append("## SEUS DEPENDENTES")
        if dependents:
            for d in dependents:
                lines.append(f"- {d}")
        else:
            lines.append("Ninguém esperando você.")
        lines.append("")

    lines.append("## RECURSOS COMPARTILHADOS")
    if resources:
        lines.append("| recurso | estado |")
        lines.append("|---|---|")
        for r, state in sorted(resources.items()):
            lines.append(f"| {r} | {state} |")
    else:
        lines.append("Nenhum recurso registrado.")
    lines.append("")

    lines.append("## EVENTOS RELEVANTES (últimos)")
    if events:
        lines.append("```")
        for ev in events:
            line = f"{ev['ts']} {ev['session']} {ev['verb']} {ev['obj']}"
            if ev["detail"]:
                line += f" {ev['detail']}"
            lines.append(line)
        lines.append("```")
    else:
        lines.append("Nada recente.")
    lines.append("")

    lines.append("## PERGUNTAS PENDENTES")
    if my_questions:
        for ts, frm, to, text in my_questions:
            lines.append(f"- [{ts}] {frm} → {to}: {text}")
    else:
        lines.append("Nenhuma.")
    lines.append("")

    return "\n".join(lines) + "\n"


def write_view_atomic(view_path: Path, content: str):
    view_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{view_path.name}.",
        suffix=".tmp",
        dir=str(view_path.parent),
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, view_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------- Daemon loop ----------

class Daemon:
    """Phase 0 daemon using ultra-fast polling on the ramdisk.

    On a tmpfs, stat() and read() are memory operations. We can poll at
    sub-millisecond intervals without meaningful CPU cost for a handful of
    small files. This avoids the "tail -F doesn't see new files" gotcha.
    """

    POLL_INTERVAL_SEC = 0.001  # 1ms

    def __init__(self, swarm_dir: Path):
        self.swarm_dir = swarm_dir
        self.log_dir = swarm_dir / "log"
        self.view_dir = swarm_dir / "view"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.view_dir.mkdir(parents=True, exist_ok=True)
        self.index = SwarmIndex()
        self.offsets = {}
        self.buffers = {}
        self.render_count = 0

    def render_all(self):
        sessions = set(self.index.sessions_known) | {"DIRECTOR"}
        for s in sessions:
            content = render_view(self.index, s)
            write_view_atomic(self.view_dir / f"{s}.md", content)
        self.render_count += 1

    def process_line(self, session: str, line: str) -> bool:
        ev = parse_event(session, line)
        if ev is None:
            return False
        self.index.apply(ev)
        return True

    def scan_once(self) -> bool:
        """Check all log files for new content. Returns True if state changed."""
        changed = False

        # Discover any new log files
        for log_file in self.log_dir.glob("*.log"):
            session = log_file.stem
            if session not in self.offsets:
                self.offsets[session] = 0
                self.buffers[session] = ""

        # Read deltas
        for session in list(self.offsets.keys()):
            log_file = self.log_dir / f"{session}.log"
            try:
                st = log_file.stat()
            except FileNotFoundError:
                continue
            if st.st_size < self.offsets[session]:
                # File was truncated/replaced; restart from beginning
                self.offsets[session] = 0
                self.buffers[session] = ""
            if st.st_size == self.offsets[session]:
                continue

            try:
                with open(log_file, "rb") as f:
                    f.seek(self.offsets[session])
                    chunk = f.read()
            except FileNotFoundError:
                continue

            self.offsets[session] += len(chunk)
            data = self.buffers[session] + chunk.decode("utf-8", errors="replace")
            lines = data.split("\n")
            # last element is either empty string (if data ends with \n) or
            # a partial line we need to buffer
            self.buffers[session] = lines[-1]
            for line in lines[:-1]:
                if self.process_line(session, line):
                    changed = True

        return changed

    def run(self):
        print(f"[mycod] watching {self.log_dir}", file=sys.stderr)
        print(f"[mycod] writing to {self.view_dir}", file=sys.stderr)
        print(f"[mycod] poll interval: {self.POLL_INTERVAL_SEC*1000:.1f}ms", file=sys.stderr)

        # Initial render so view files exist even if no events yet
        (self.log_dir / "DIRECTOR.log").touch(exist_ok=True)
        self.index.sessions_known.add("DIRECTOR")
        self.render_all()

        try:
            while True:
                if self.scan_once():
                    self.render_all()
                time.sleep(self.POLL_INTERVAL_SEC)
        except KeyboardInterrupt:
            pass


def main():
    if len(sys.argv) < 2:
        print("usage: mycod.py <swarm_dir>", file=sys.stderr)
        sys.exit(2)
    swarm_dir = Path(sys.argv[1]).resolve()
    Daemon(swarm_dir).run()


if __name__ == "__main__":
    main()
