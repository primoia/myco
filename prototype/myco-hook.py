#!/usr/bin/env python3
"""
myco-hook.py — Claude Code Stop hook for the myco prototype.

When Claude finishes a turn, this script is invoked by Claude Code with a
JSON payload on stdin describing the turn (session_id, transcript_path,
cwd, ...). The script reads the JSONL transcript, finds the last
<myco>...</myco> block in the assistant's text output for that turn, and
appends each event line to log/<session>.log in the swarm directory.

This removes the need for Claude to call `myco-log` explicitly via Bash
tool calls. Claude just writes a tag block at the end of its turn and the
hook converts it into log events that the daemon (mycod.py) picks up.

Usage:
  - Configure as a Stop hook in .claude/settings.json
  - Set MYCO_SWARM to the swarm dir (default: /mnt/ramdisk/myco)
  - Set MYCO_SESSION to override the session name (default: cwd basename)

Block format inside <myco>...</myco>:

    <myco>
    start webhook.incoming
    need IAM.auth.v2
    # comments and blank lines are ignored
    </myco>

Each non-empty, non-comment line is one event: "<verb> <obj> [detail...]"
The first token must be one of the protocol verbs.

Race condition note:
  Claude Code can fire the Stop hook before the final assistant message
  has been flushed to the transcript JSONL. The hook polls the transcript
  for up to ~500ms waiting for the assistant text to appear. If it still
  isn't there when the poll times out, the hook exits silently.
"""

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

TAG_RE = re.compile(r"<myco>(.*?)</myco>", re.DOTALL | re.IGNORECASE)

VALID_VERBS = {
    "start", "done", "need", "block",
    "up", "down", "direct", "ask", "note", "log", "reply", "say",
}


def debug(msg: str) -> None:
    if os.environ.get("MYCO_HOOK_DEBUG"):
        print(f"[myco-hook] {msg}", file=sys.stderr)


def read_payload() -> dict:
    try:
        data = sys.stdin.read()
    except OSError:
        return {}
    if not data:
        return {}
    try:
        return json.loads(data)
    except (json.JSONDecodeError, ValueError) as e:
        debug(f"failed to parse stdin payload: {e}")
        return {}


def extract_text(message) -> str:
    """Pull text blocks out of a transcript message dict."""
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def _scan_tail_for_assistant(lines: list) -> str:
    """Walk lines backwards, collecting consecutive assistant text blocks
    until a user message is hit. Returns '' if nothing found.
    """
    chunks = []
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            # partial line being written by Claude Code; skip
            continue
        etype = entry.get("type")
        if etype == "user":
            break
        if etype == "assistant":
            txt = extract_text(entry.get("message"))
            if txt:
                chunks.append(txt)
    return "\n".join(reversed(chunks))


def last_assistant_text(transcript_path: str, wait_ms: int = 500) -> str:
    """Read the JSONL transcript and return the text of the most recent
    assistant turn. Polls up to wait_ms because Claude Code sometimes fires
    the Stop hook before the assistant message has been flushed to disk.
    """
    if not transcript_path:
        return ""
    p = Path(transcript_path)

    poll_interval_s = 0.02
    deadline_ns = time.monotonic_ns() + wait_ms * 1_000_000

    while True:
        if p.exists():
            try:
                lines = p.read_text(errors="replace").splitlines()
            except OSError as e:
                debug(f"failed to read transcript: {e}")
                lines = []
            text = _scan_tail_for_assistant(lines)
            if text:
                return text

        if time.monotonic_ns() >= deadline_ns:
            debug(f"transcript poll timeout ({wait_ms}ms): no assistant text yet")
            return ""
        time.sleep(poll_interval_s)


def parse_block(block_text: str) -> list:
    events = []
    for raw in block_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        first = line.split(None, 1)[0].lower()
        if first not in VALID_VERBS:
            debug(f"skipping unknown verb in line: {line!r}")
            continue
        events.append(line)
    return events


def session_name(payload: dict) -> str:
    # Session names are uppercase throughout the protocol. Normalize at
    # the hook boundary so the event log, the daemon index, and view
    # filters all agree regardless of what was typed in the launcher.
    name = os.environ.get("MYCO_SESSION")
    if name:
        return name.upper()
    cwd = payload.get("cwd") or os.getcwd()
    return (Path(cwd).name or "default").upper()


def swarm_dir() -> Path:
    return Path(os.environ.get("MYCO_SWARM", "/mnt/ramdisk/myco"))


def append_events_fs(session: str, events: list) -> None:
    log_dir = swarm_dir() / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{session}.log"
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(log_file, "a") as f:
        for ev in events:
            f.write(f"{ts} {session} {ev}\n")
    debug(f"appended {len(events)} event(s) to {log_file}")


def _make_headers() -> dict:
    """Build HTTP headers, including auth token if configured."""
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("MYCO_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def post_events_http(session: str, events: list) -> bool:
    """POST events to the daemon via HTTP. Retries once before giving up."""
    url = os.environ.get("MYCO_URL")
    if not url:
        return False
    data = json.dumps({"session": session, "events": events}).encode()
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                f"{url}/events",
                data=data,
                headers=_make_headers(),
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                return resp.status == 200
        except Exception as e:
            if attempt == 0:
                debug(f"HTTP POST attempt 1 failed ({e}), retrying in 100ms")
                time.sleep(0.1)
            else:
                debug(f"HTTP POST attempt 2 failed ({e}), falling back to filesystem")
    return False


def main() -> int:
    payload = read_payload()
    debug(f"payload keys: {list(payload.keys())}")

    tp = payload.get("transcript_path", "")
    text = last_assistant_text(tp)
    # Fall back to last_assistant_message if the payload happens to carry it
    # (it doesn't in current Claude Code, but defensive)
    if not text:
        text = payload.get("last_assistant_message") or ""
    debug(f"text extracted: {len(text)} chars")

    if not text:
        debug("no assistant text found for this turn")
        return 0

    matches = TAG_RE.findall(text)
    if not matches:
        debug("no <myco> block in last turn")
        return 0

    # Last block wins, so Claude can draft and revise within one turn.
    events = parse_block(matches[-1])
    if not events:
        debug("<myco> block parsed to zero events")
        return 0

    session = session_name(payload)
    if os.environ.get("MYCO_URL"):
        # Daemon is authoritative. If POST fails, drop the events on the
        # floor rather than silently writing them to a local swarm dir
        # the daemon doesn't know about.
        if not post_events_http(session, events):
            debug(f"HTTP POST failed and MYCO_URL is set; {len(events)} event(s) dropped")
    else:
        append_events_fs(session, events)
    return 0


if __name__ == "__main__":
    sys.exit(main())
