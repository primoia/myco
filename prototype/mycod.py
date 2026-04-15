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

import json
import os
import re
import sys
import time
import tempfile
import threading
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs


# ---------- Event parsing ----------

_KNOWN_KV_KEYS = {"ref", "spec", "ack"}
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
        key = m.group(1)
        if key not in _KNOWN_KV_KEYS:
            continue
        kvs[key] = m.group(2)
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
    # parts[1] is the session id declared in the line; we trust the filename
    verb = parts[2]
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
        self.answered_specs = set()        # spec ids that have been acked
        self.resolved_questions = set()    # (frm, to, ts) tuples resolved by reply
        self.last_seen = {}                  # session → timestamp string
        self.broadcasts = []                 # (ts, session, text) from say verb

    def apply(self, ev):
        s = ev["session"]
        self.sessions_known.add(s)
        self.events.append(ev)
        self.last_seen[s] = ev["ts"]

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
            # v1: track msg targets from spec: kvs
            msg_id = kvs.get("spec")
            if msg_id:
                self.msg_targets[msg_id] = obj  # obj = target session
            # Session that asks is clearly active
            if self.session_status.get(s) in (None, "unknown"):
                self.session_status[s] = "active"
                self.session_action[s] = f"ask {obj}"
        elif verb == "reply":
            # reply TARGET answer — resolves pending questions from TARGET→self
            ack_id = kvs.get("ack")
            if ack_id:
                self.msg_acks[ack_id].add(s)
                self.answered_specs.add(ack_id)
            spec_id = kvs.get("spec")
            if spec_id:
                self.msg_targets[spec_id] = obj  # obj = target session
            # Resolve all open questions from target→self
            self._resolve_questions_between(obj, s)
            if self.session_status.get(s) in (None, "unknown"):
                self.session_status[s] = "active"
                self.session_action[s] = f"reply {obj}"
        elif verb == "say":
            # Broadcast visible to all sessions
            self.broadcasts.append((ev["ts"], s, f"{obj} {detail_text}".strip()))
            if s not in self.session_status or self.session_status[s] == "unknown":
                self.session_status[s] = "active"
                self.session_action[s] = f"say {obj}"
        elif verb == "note":
            # v1: track ack for messages and resolve associated questions
            ack_id = kvs.get("ack")
            if ack_id:
                self.msg_acks[ack_id].add(s)
                self.answered_specs.add(ack_id)
            # note events update last-seen but don't override active/blocked
            if s not in self.session_status or self.session_status[s] == "unknown":
                self.session_status[s] = "active"
                self.session_action[s] = f"note {obj}"

    def _resolve_questions_between(self, asker: str, replier: str):
        """Mark all open questions from asker→replier as resolved.
        Also acks any associated spec: messages."""
        for ts, frm, to, detail in self.questions:
            if frm == asker and to == replier:
                self.resolved_questions.add((frm, to, ts))
                # Auto-ack the spec if present
                _, q_kvs = parse_detail_kvs(detail)
                spec_id = q_kvs.get("spec")
                if spec_id:
                    self.msg_acks[spec_id].add(replier)
                    self.answered_specs.add(spec_id)

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

        # Directives and broadcasts: always visible
        if verb in ("direct", "say"):
            return True

        # Questions addressed to us: always visible
        if verb == "ask" and ev["obj"] == session:
            return True

        # Replies: only visible to sender and target (private channel)
        if verb == "reply":
            return ev["obj"] == session

        # Notes: filtered by type
        if verb == "note":
            if s == session:
                return True  # already caught above, but explicit
            kvs = ev.get("kvs", {})
            ack_id = kvs.get("ack")
            if ack_id:
                # Ack notes visible only to the session that sent the original msg
                # msg_id like "msg/CART-001.md" → sender is "CART" (prefix before dash)
                # But more reliably: check who asked with this spec
                for q_ts, q_frm, q_to, q_detail in self.questions:
                    _, q_kvs = parse_detail_kvs(q_detail)
                    if q_kvs.get("spec") == ack_id and q_frm == session:
                        return True
                return False
            # Other notes from others: hide (spam filter)
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
            if ev["verb"] in ("ask", "reply"):
                kvs = ev.get("kvs", {})
                msg_id = kvs.get("spec")
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

QUESTION_TTL_SECONDS = 1800  # 30 minutes


def _parse_ts(ts_str: str) -> float:
    """Parse ISO timestamp to epoch seconds. Returns 0.0 on failure."""
    try:
        return time.mktime(time.strptime(ts_str, "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return 0.0


def _age_label(ts_str: str) -> str:
    """Human-readable age from an ISO timestamp."""
    epoch = _parse_ts(ts_str)
    if epoch == 0.0:
        return "?"
    delta = time.time() - epoch
    if delta < 60:
        return f"{int(delta)}s"
    if delta < 3600:
        return f"{int(delta // 60)}min"
    return f"{delta / 3600:.1f}h"


def render_view(index: SwarmIndex, session: str, swarm_dir: Path = None,
                session_dirs: dict = None) -> str:
    blockers = index.blockers_for(session)
    dependents = index.dependents_of(session)
    resources = dict(index.resources)
    directives = list(index.directives)
    events = index.recent_events_for(session, limit=15)
    status = index.session_status.get(session, "unknown")
    action = index.session_action.get(session, "no recent action")
    now = time.time()
    # Filter questions: only show those relevant to this session, not answered, not expired
    my_questions = []
    for q in index.questions:
        ts, frm, to, detail = q
        if frm != session and to != session:
            continue
        # Check if this question has a spec: that was acked
        _, q_kvs = parse_detail_kvs(detail)
        spec_id = q_kvs.get("spec")
        if spec_id and spec_id in index.answered_specs:
            continue
        # Check if resolved by a reply
        if (frm, to, ts) in index.resolved_questions:
            continue
        # TTL: skip questions older than threshold
        q_epoch = _parse_ts(ts)
        if q_epoch > 0 and (now - q_epoch) > QUESTION_TTL_SECONDS:
            continue
        my_questions.append(q)
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
            lines.append("| sessão | status | última ação | last-seen | bloqueadores | dependentes |")
            lines.append("|---|---|---|---|---|---|")
            for s in workers:
                st = index.session_status.get(s, "unknown")
                ac = index.session_action.get(s, "—")
                ls = _age_label(index.last_seen.get(s, "")) if index.last_seen.get(s) else "—"
                bl = ", ".join(index.blockers_for(s)) or "—"
                dp = ", ".join(index.dependents_of(s)) or "—"
                lines.append(f"| {s} | {st} | {ac} | {ls} | {bl} | {dp} |")
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
        lines.append("| sessão | artefato | ref | path | spec |")
        lines.append("|---|---|---|---|---|")
        for a in index.artifacts:
            s_dir = (session_dirs or {}).get(a["session"], "")
            ref = a["ref"] or "—"
            spec = a["spec"] or "—"
            path = s_dir or "—"
            lines.append(f"| {a['session']} | {a['obj']} | {ref} | {path} | {spec} |")
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

    # BROADCASTS (say verb)
    if index.broadcasts:
        lines.append("## BROADCASTS")
        for ts, sender, text in index.broadcasts[-5:]:
            lines.append(f"- [{ts}] **{sender}**: {text}")
        lines.append("")

    # PEERS (last-seen) — worker views only
    if session != "DIRECTOR":
        peers = sorted(s for s in index.sessions_known if s != session and s != "DIRECTOR")
        if peers:
            lines.append("## PEERS")
            for p in peers:
                ls_ts = index.last_seen.get(p)
                ls = _age_label(ls_ts) if ls_ts else "—"
                st = index.session_status.get(p, "unknown")
                lines.append(f"- **{p}**: {st}, last-seen {ls}")
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
            lines.append(f"- De **{msg['sender']}**: `{msg['id']}` — leia com `curl $MYCO_URL/{msg['id']}` ou `Read {msg['path']}` e faça `note ack ack:{msg['id']}`")
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
        self.session_dirs = self._load_session_dirs()
        self.lock = threading.Lock()
        self.view_cache = {}
        self.start_time = time.time()

    def _load_session_dirs(self) -> dict:
        """Load session→project_dir mapping from .myco-state.json."""
        state_file = self.swarm_dir / ".myco-state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text())
                return state.get("sessions", {})
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def render_all(self):
        sessions = set(self.index.sessions_known) | {"DIRECTOR"}
        for s in sessions:
            content = render_view(self.index, s, swarm_dir=self.swarm_dir,
                                  session_dirs=self.session_dirs)
            self.view_cache[s] = content
            write_view_atomic(self.view_dir / f"{s}.md", content)
        self.render_count += 1

    def _render_to_cache(self):
        """Render all views to in-memory cache only (no filesystem writes).
        Caller must hold self.lock."""
        sessions = set(self.index.sessions_known) | {"DIRECTOR"}
        for s in sessions:
            self.view_cache[s] = render_view(
                self.index, s, swarm_dir=self.swarm_dir,
                session_dirs=self.session_dirs,
            )
        self.render_count += 1

    def ingest_events(self, session: str, event_lines: list):
        """Thread-safe ingestion of events from HTTP POST.
        Persists to log file and updates index + view cache.
        Advances the file offset so scan_once won't re-process these lines."""
        with self.lock:
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            log_file = self.log_dir / f"{session}.log"
            with open(log_file, "a") as f:
                for ev_line in event_lines:
                    full_line = f"{ts} {session} {ev_line}"
                    f.write(full_line + "\n")
                    self.process_line(session, full_line)
                # Advance offset so poll loop skips what we just wrote
                new_size = f.tell()
            if session not in self.offsets:
                self.offsets[session] = 0
                self.buffers[session] = ""
            self.offsets[session] = new_size
            self._render_to_cache()

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

    def run(self, port: int = 0):
        # Initial setup: ensure DIRECTOR exists, replay logs, render
        (self.log_dir / "DIRECTOR.log").touch(exist_ok=True)
        self.index.sessions_known.add("DIRECTOR")
        self.scan_once()
        self.render_all()

        if port:
            self._run_http(port)
        else:
            self._run_poll()

    def _run_http(self, port: int):
        server = MycoHTTPServer(("", port), MycoHandler, self)
        print(f"[mycod] HTTP server on port {port}", file=sys.stderr)
        print(f"[mycod] swarm dir: {self.swarm_dir}", file=sys.stderr)
        # Run HTTP server in a background thread so we can poll logs too
        http_thread = threading.Thread(target=server.serve_forever, daemon=True)
        http_thread.start()
        print(f"[mycod] polling {self.log_dir} (hybrid mode: HTTP + filesystem)", file=sys.stderr)
        try:
            while True:
                changed = False
                with self.lock:
                    changed = self.scan_once()
                    if changed:
                        self._render_to_cache()
                        # Also write to filesystem for local readers
                        sessions = set(self.index.sessions_known) | {"DIRECTOR"}
                        for s in sessions:
                            content = self.view_cache.get(s, "")
                            if content:
                                write_view_atomic(self.view_dir / f"{s}.md", content)
                        if self.verbose:
                            now = time.strftime("%H:%M:%S")
                            slist = sorted(self.index.sessions_known)
                            print(f"[mycod {now}] rendered {len(slist)} views ({', '.join(slist)})", file=sys.stderr)
                time.sleep(self.POLL_INTERVAL_SEC)
        except KeyboardInterrupt:
            server.shutdown()

    def _run_poll(self):
        print(f"[mycod] watching {self.log_dir}", file=sys.stderr)
        print(f"[mycod] writing to {self.view_dir}", file=sys.stderr)
        print(f"[mycod] poll interval: {self.POLL_INTERVAL_SEC*1000:.1f}ms", file=sys.stderr)

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



# ---------- HTTP server ----------

class MycoHTTPServer(ThreadingHTTPServer):
    """HTTP server that holds a reference to the Daemon instance."""

    def __init__(self, server_address, handler_class, daemon: Daemon):
        self.daemon_ref = daemon  # avoid shadowing socketserver.BaseServer.daemon
        self.auth_token = os.environ.get("MYCO_TOKEN", "")
        super().__init__(server_address, handler_class)


class MycoHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the myco daemon."""

    def _check_auth(self) -> bool:
        """Validate Bearer token if MYCO_TOKEN is configured. Returns True if ok."""
        token = self.server.auth_token
        if not token:
            return True  # no auth configured
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {token}":
            return True
        self._respond(401, json.dumps({"ok": False, "error": "unauthorized"}),
                      content_type="application/json")
        return False

    def do_GET(self):
        if self.path == "/healthz":
            # Health check — no auth required
            daemon = self.server.daemon_ref
            uptime = time.time() - daemon.start_time
            body = json.dumps({
                "ok": True,
                "uptime_s": round(uptime, 1),
                "sessions": len(daemon.index.sessions_known),
            })
            self._respond(200, body, content_type="application/json")
            return
        if not self._check_auth():
            return
        if self.path.startswith("/view/"):
            session = self.path[6:].strip("/").upper()
            daemon = self.server.daemon_ref
            with daemon.lock:
                view = daemon.view_cache.get(session, "")
            self._respond(200, view, content_type="text/markdown; charset=utf-8")
        elif self.path.startswith("/msg/"):
            parsed = urlparse(self.path)
            filename = parsed.path[5:].strip("/")
            if not filename or "/" in filename or ".." in filename:
                self._respond(400, "invalid filename")
                return
            msg_file = self.server.daemon_ref.swarm_dir / "msg" / filename
            if not msg_file.exists():
                self._respond(404, "not found")
                return
            content = msg_file.read_text(errors="replace")
            # Auto-ack: if ?session=X is provided, mark msg as read by that session
            qs = parse_qs(parsed.query)
            reader = qs.get("session", [None])[0]
            if reader:
                msg_id = f"msg/{filename}"
                daemon = self.server.daemon_ref
                with daemon.lock:
                    daemon.index.msg_acks[msg_id].add(reader.upper())
                    daemon.index.answered_specs.add(msg_id)
                    daemon._render_to_cache()
            self._respond(200, content, content_type="text/markdown; charset=utf-8")
        elif self.path == "/status":
            daemon = self.server.daemon_ref
            with daemon.lock:
                status = self._build_status()
            self._respond(200, json.dumps(status), content_type="application/json")
        else:
            self._respond(404, "not found")

    def do_POST(self):
        if not self._check_auth():
            return
        if self.path == "/events":
            body = self._read_body()
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                self._respond(400, json.dumps({"ok": False, "error": "invalid JSON"}),
                              content_type="application/json")
                return
            session = data.get("session", "").upper()
            events = data.get("events", [])
            if not session or not events:
                self._respond(400, json.dumps({"ok": False, "error": "missing session or events"}),
                              content_type="application/json")
                return
            self.server.daemon_ref.ingest_events(session, events)
            self._respond(200, json.dumps({"ok": True, "count": len(events)}),
                          content_type="application/json")
        elif self.path.startswith("/msg/"):
            filename = self.path[5:].strip("/")
            if not filename or "/" in filename or ".." in filename:
                self._respond(400, json.dumps({"ok": False, "error": "invalid filename"}),
                              content_type="application/json")
                return
            body = self._read_body()
            msg_dir = self.server.daemon_ref.swarm_dir / "msg"
            msg_dir.mkdir(parents=True, exist_ok=True)
            (msg_dir / filename).write_text(body)
            self._respond(200, json.dumps({"ok": True}),
                          content_type="application/json")
        elif self.path.startswith("/dispatch/"):
            session = self.path[10:].strip("/").upper()
            body = self._read_body()
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                self._respond(400, json.dumps({"ok": False, "error": "invalid JSON"}),
                              content_type="application/json")
                return
            prompt = data.get("prompt", "")
            if not prompt:
                self._respond(400, json.dumps({"ok": False, "error": "missing prompt"}),
                              content_type="application/json")
                return
            dispatch_dir = self.server.daemon_ref.swarm_dir / "dispatch"
            dispatch_dir.mkdir(parents=True, exist_ok=True)
            dispatch_file = dispatch_dir / f"{session}.prompt"
            dispatch_file.write_text(prompt)
            self._respond(200, json.dumps({"ok": True}),
                          content_type="application/json")
        else:
            self._respond(404, "not found")

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8")

    def _respond(self, code: int, body: str, content_type: str = "text/plain"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        encoded = body.encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _build_status(self) -> dict:
        daemon = self.server.daemon_ref
        sessions = {}
        for s in sorted(daemon.index.sessions_known):
            sessions[s] = {
                "status": daemon.index.session_status.get(s, "unknown"),
                "action": daemon.index.session_action.get(s, ""),
                "blockers": daemon.index.blockers_for(s),
                "dependents": daemon.index.dependents_of(s),
            }
        return {"sessions": sessions}

    def log_message(self, format, *args):
        if self.server.daemon_ref.verbose:
            sys.stderr.write(f"[mycod-http] {format % args}\n")


def main():
    quiet = "--quiet" in sys.argv or "-q" in sys.argv
    port = 0
    args_raw = sys.argv[1:]
    # Parse --port
    filtered = []
    i = 0
    while i < len(args_raw):
        if args_raw[i] == "--port" and i + 1 < len(args_raw):
            port = int(args_raw[i + 1])
            i += 2
        elif args_raw[i].startswith("--port="):
            port = int(args_raw[i].split("=", 1)[1])
            i += 1
        elif args_raw[i] in ("-q", "--quiet"):
            i += 1
        else:
            filtered.append(args_raw[i])
            i += 1
    if not filtered:
        print("usage: mycod.py [-q|--quiet] [--port PORT] <swarm_dir>", file=sys.stderr)
        sys.exit(2)
    swarm_dir = Path(filtered[0]).resolve()
    Daemon(swarm_dir, verbose=not quiet).run(port=port)


if __name__ == "__main__":
    main()
