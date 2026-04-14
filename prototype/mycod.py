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

Protocol v1. See docs/PROTOCOL.md for the event format.
"""

import os
import re
import sys
import time
import tempfile
from collections import defaultdict, deque
from pathlib import Path


# ---------- Event parsing ----------

_KV_RE = re.compile(r'\b([a-z]+):(\S+)')


def parse_detail_kvs(detail: str):
    """Extract key:value pairs from a detail string.

    Returns (free_text, kvs_dict). Keys are lowercase single words,
    values are non-whitespace strings. The free_text has the kv pairs
    removed. Events without kv pairs return (detail, {}).
    """
    kvs = {}
    spans = []
    for m in _KV_RE.finditer(detail):
        kvs[m.group(1)] = m.group(2)
        spans.append((m.start(), m.end()))
    if not spans:
        return detail, {}
    # Build free text by removing kv spans
    parts = []
    prev = 0
    for start, end in spans:
        parts.append(detail[prev:start])
        prev = end
    parts.append(detail[prev:])
    free_text = " ".join(parts).split()
    return " ".join(free_text), kvs


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
    detail_text, kvs = parse_detail_kvs(detail)
    return {
        "ts": ts,
        "session": session,
        "verb": verb,
        "obj": obj,
        "detail": detail,
        "detail_text": detail_text,
        "kvs": kvs,
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
        # v1: artifacts never expire (every done is permanent)
        self.artifacts = []
        # v1: message tracking (msg/ directory)
        self.msg_acks = defaultdict(set)   # msg_id → sessions that acked
        self.msg_targets = {}              # msg_id → target session

    def apply(self, ev):
        s = ev["session"]
        self.sessions_known.add(s)
        self.events.append(ev)

        verb = ev["verb"]
        obj = ev["obj"]
        detail = ev["detail"]
        kvs = ev.get("kvs", {})

        # Resource names can be multi-token: "up container iam-db"
        # We concatenate obj + detail for resource verbs
        detail_text = ev.get("detail_text", detail)
        full_obj = f"{obj} {detail_text}".strip() if detail_text else obj

        if verb == "start":
            self.session_status[s] = "active"
            self.session_action[s] = f"start {obj}"
        elif verb == "done":
            self.session_status[s] = "idle"
            self.session_action[s] = f"done {obj}"
            artifact = f"{s}.{obj}"
            self.provides[s].add(artifact)
            self.provides[s].add(obj)
            # v1: permanent artifact record
            self.artifacts.append({
                "ts": ev["ts"],
                "session": s,
                "obj": obj,
                "ref": kvs.get("ref", ""),
                "spec": kvs.get("spec", ""),
            })
        elif verb == "need":
            self.needs[s].add(obj)
        elif verb == "block":
            self.session_status[s] = "blocked"
            self.session_action[s] = f"blocked: {obj} {detail_text}".strip()
        elif verb == "up":
            self.resources[full_obj] = "UP"
        elif verb == "down":
            self.resources[full_obj] = "DOWN"
        elif verb == "direct":
            self.directives.append((ev["ts"], obj, detail))
        elif verb == "ask":
            self.questions.append((ev["ts"], s, obj, detail))
            # v1: track msg targets from spec: or msg: kvs
            msg_id = kvs.get("spec") or kvs.get("msg")
            if msg_id:
                self.msg_targets[msg_id] = obj  # obj = target session
        elif verb == "note":
            # v1: track ack for messages
            ack_id = kvs.get("ack")
            if ack_id:
                self.msg_acks[ack_id].add(s)
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

    # ---------- Visibility filters ----------
    # Phase 0: all-see-all. Every session sees every event from every
    # other session (except note spam). When swarms grow beyond 5-10
    # sessions, replace _is_visible with a smarter filter:
    #
    # Ideas for future filters:
    #   - dependency-based: only show upstream/downstream (original design)
    #   - topic-based: tag events with topics, filter by relevance
    #   - tiered: status verbs (start/done/block) visible to all,
    #             detail verbs (note/ask) filtered by relationship
    #   - explicit subscription: sessions declare what they watch

    def _is_visible(self, ev, session: str) -> bool:
        """Decide if `ev` should appear in `session`'s view.
        Override this method to change visibility rules."""
        s = ev["session"]
        verb = ev["verb"]

        # Own events: always visible
        if s == session:
            return True

        # Directives: always visible
        if verb == "direct":
            return True

        # Questions addressed to us: always visible
        if verb == "ask" and ev["obj"] == session:
            return True

        # Note spam from others: hide
        if verb == "note" and s != session:
            return False

        # All other events from other sessions: visible
        return True

    def pending_msgs_for(self, session: str, msg_dir: Path):
        """Return list of pending (unacked) messages targeted at `session`.

        Scans msg/*.md files, cross-references with msg_targets and msg_acks.
        A message is pending if:
          - it's listed in msg_targets with target == session, AND
          - session has not acked it (not in msg_acks[msg_id])
        Returns list of dicts: {"id": msg_id, "path": path, "sender": ...}
        """
        pending = []
        if not msg_dir.is_dir():
            return pending
        # Build reverse map: msg path fragment → sender session
        # msg_targets keys are like "msg/CART-001.md"
        target_to_sender = {}
        for ev in self.events:
            if ev["verb"] == "ask":
                kvs = ev.get("kvs", {})
                msg_id = kvs.get("spec") or kvs.get("msg")
                if msg_id and self.msg_targets.get(msg_id) == session:
                    target_to_sender[msg_id] = ev["session"]

        for msg_file in sorted(msg_dir.glob("*.md")):
            msg_id = f"msg/{msg_file.name}"
            # Check if this message is targeted at this session
            if msg_id not in target_to_sender:
                continue
            # Check if already acked
            if session in self.msg_acks.get(msg_id, set()):
                continue
            pending.append({
                "id": msg_id,
                "path": str(msg_file),
                "sender": target_to_sender[msg_id],
            })
        return pending

    def recent_events_for(self, session: str, limit=15):
        relevant = []
        for ev in reversed(self.events):
            if self._is_visible(ev, session):
                relevant.append(ev)
            if len(relevant) >= limit:
                break
        return list(reversed(relevant[:limit]))


# ---------- Rendering ----------

def render_view(index: SwarmIndex, session: str, swarm_dir: Path = None) -> str:
    blockers = index.blockers_for(session)
    dependents = index.dependents_of(session)
    resources = dict(index.resources)
    directives = list(index.directives)
    events = index.recent_events_for(session, limit=15)
    status = index.session_status.get(session, "unknown")
    action = index.session_action.get(session, "no recent action")
    my_questions = [q for q in index.questions if q[1] == session or q[2] == session]
    msg_dir = swarm_dir / "msg" if swarm_dir else None
    pending_msgs = index.pending_msgs_for(session, msg_dir) if msg_dir else []

    lines = []
    lines.append("<!-- myco protocol v1 -->")
    lines.append(f"# myco view — {session}")
    lines.append("")
    lines.append("## AGORA")
    if session == "DIRECTOR":
        workers = sorted(s for s in index.sessions_known if s != "DIRECTOR")
        lines.append(f"Swarm com {len(workers)} sessões worker ativas.")
        if workers:
            lines.append("")
            lines.append("| sessão | status | última ação | bloqueadores | dependentes |")
            lines.append("|---|---|---|---|---|")
            for s in workers:
                st = index.session_status.get(s, "unknown")
                ac = index.session_action.get(s, "—")
                bl = ", ".join(index.blockers_for(s)) or "—"
                dp = ", ".join(index.dependents_of(s)) or "—"
                lines.append(f"| {s} | {st} | {ac} | {bl} | {dp} |")
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

    # v1: ARTEFATOS PUBLICADOS (permanent, never capped)
    lines.append("## ARTEFATOS PUBLICADOS")
    if index.artifacts:
        lines.append("| sessão | artefato | ref | spec |")
        lines.append("|---|---|---|---|")
        for a in index.artifacts:
            lines.append(f"| {a['session']} | {a['obj']} | {a['ref'] or '—'} | {a['spec'] or '—'} |")
    else:
        lines.append("Nenhum artefato publicado.")
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

    # DIRECTOR: dependency graph and conflict detection
    if session == "DIRECTOR":
        lines.append("## GRAFO DE DEPENDÊNCIAS")
        has_deps = False
        for s in sorted(index.sessions_known):
            if s == "DIRECTOR":
                continue
            for need in sorted(index.needs.get(s, set())):
                if not index.satisfied(need):
                    # Find who might provide it
                    provider = need.split(".")[0] if "." in need else "?"
                    lines.append(f"- {s} --espera--> {provider}.{need}")
                    has_deps = True
        if not has_deps:
            lines.append("Nenhuma dependência pendente.")
        lines.append("")

        lines.append("## CONFLITOS DETECTADOS")
        # Detect sessions working on same object simultaneously
        active_objects = defaultdict(list)
        for s in sorted(index.sessions_known):
            if s == "DIRECTOR":
                continue
            st = index.session_status.get(s, "unknown")
            if st == "active":
                ac = index.session_action.get(s, "")
                if ac.startswith("start "):
                    obj = ac[6:]
                    active_objects[obj].append(s)
        conflicts = {obj: sessions for obj, sessions in active_objects.items() if len(sessions) > 1}
        if conflicts:
            for obj, sessions in sorted(conflicts.items()):
                lines.append(f"- ATENÇÃO: {', '.join(sessions)} trabalhando em `{obj}` simultaneamente")
        else:
            lines.append("Nenhum conflito detectado.")
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

    lines.append("## EVENTOS RELEVANTES (últimos 15)")
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

    # v1: MENSAGENS PENDENTES (from msg/ directory)
    lines.append("## MENSAGENS PENDENTES")
    if pending_msgs:
        for msg in pending_msgs:
            lines.append(f"- De **{msg['sender']}**: `{msg['id']}` (path: `{msg['path']}`) — leia com Read e faça `note ack ack:{msg['id']}`")
    else:
        lines.append("Nenhuma mensagem pendente.")
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

    def __init__(self, swarm_dir: Path, verbose: bool = False):
        self.swarm_dir = swarm_dir
        self.log_dir = swarm_dir / "log"
        self.view_dir = swarm_dir / "view"
        self.msg_dir = swarm_dir / "msg"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.view_dir.mkdir(parents=True, exist_ok=True)
        self.msg_dir.mkdir(parents=True, exist_ok=True)
        self.index = SwarmIndex()
        self.offsets = {}
        self.buffers = {}
        self.render_count = 0
        self.verbose = verbose

    def render_all(self):
        sessions = set(self.index.sessions_known) | {"DIRECTOR"}
        for s in sessions:
            content = render_view(self.index, s, swarm_dir=self.swarm_dir)
            write_view_atomic(self.view_dir / f"{s}.md", content)
        self.render_count += 1

    def process_line(self, session: str, line: str) -> bool:
        ev = parse_event(session, line)
        if ev is None:
            return False
        self.index.apply(ev)
        if self.verbose:
            now = time.strftime("%H:%M:%S")
            detail = f" {ev['detail']}" if ev["detail"] else ""
            print(f"[mycod {now}] {session}: {ev['verb']} {ev['obj']}{detail}", file=sys.stderr)
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
                    if self.verbose:
                        now = time.strftime("%H:%M:%S")
                        sessions = sorted(self.index.sessions_known)
                        print(f"[mycod {now}] rendered {len(sessions)} views ({', '.join(sessions)})", file=sys.stderr)
                time.sleep(self.POLL_INTERVAL_SEC)
        except KeyboardInterrupt:
            pass


def main():
    quiet = "--quiet" in sys.argv or "-q" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        print("usage: mycod.py [-q|--quiet] <swarm_dir>", file=sys.stderr)
        sys.exit(2)
    swarm_dir = Path(args[0]).resolve()
    Daemon(swarm_dir, verbose=not quiet).run()


if __name__ == "__main__":
    main()
