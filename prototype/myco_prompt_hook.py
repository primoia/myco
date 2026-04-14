#!/usr/bin/env python3
"""
myco_prompt_hook.py — Claude Code UserPromptSubmit hook for myco.

Injects the current myco view for the active session as additionalContext
on every user prompt. The goal is to replace fragile induction ("please
Read view/$EU.md before acting") with mechanical injection: the view is
always present at turn start, zero tool calls required.

Contract:
  - Opt-in via MYCO_INJECT_VIEW=1. If unset, the hook is a pure no-op.
    This protects everyday work in the myco repo itself from surprise
    injection.
  - Slash commands (prompt starts with "/") get no injection: /clear,
    /compact, /help etc. should not be polluted by swarm context.
  - Output is plain text markdown on stdout. Claude Code treats plain
    text stdout from a UserPromptSubmit hook as additionalContext. We do
    not emit JSON — that avoids the footgun of a stray print() debug
    call corrupting the hook payload.
  - Silent no-op on any error: empty view, missing swarm dir, missing
    log dir, unexpected exception. The hook must never block the user's
    prompt due to its own bugs.
  - Debug via MYCO_HOOK_DEBUG (same env var as myco-hook.py, not a new
    one). Debug output goes to stderr.

Unlike the Stop hook, we do NOT read the transcript JSONL. The
UserPromptSubmit event fires before the prompt has been appended to the
transcript, so there is no race to poll for — the prompt is already in
the payload Claude Code hands us on stdin.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

# Make sibling modules importable regardless of cwd.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from myco_view import render_view_for_session  # noqa: E402


# ---------- Helpers copied verbatim from myco-hook.py ----------
# Keeping these as a deliberate duplication rather than extracting a
# shared myco_core module. For Phase 0, simplicity of coexistence with
# the existing Stop hook outweighs DRY. If these helpers ever diverge,
# the divergence will show up in review for both files at once.

def debug(msg: str) -> None:
    if os.environ.get("MYCO_HOOK_DEBUG"):
        print(f"[myco-prompt-hook] {msg}", file=sys.stderr)


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


def session_name(payload: dict) -> str:
    name = os.environ.get("MYCO_SESSION")
    if name:
        return name
    cwd = payload.get("cwd") or os.getcwd()
    return Path(cwd).name or "default"


def swarm_dir() -> Path:
    return Path(os.environ.get("MYCO_SWARM", "/mnt/ramdisk/myco"))


def fetch_view_http(session: str) -> str:
    """GET the view from the daemon via HTTP. Returns "" on failure."""
    url = os.environ.get("MYCO_URL")
    if not url:
        return ""
    try:
        req = urllib.request.Request(f"{url}/view/{session}")
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8")
    except Exception as e:
        debug(f"HTTP GET view failed ({e}), falling back to filesystem")
    return ""


# ---------- Hook main ----------

def main() -> int:
    if os.environ.get("MYCO_INJECT_VIEW") != "1":
        debug("MYCO_INJECT_VIEW != 1, skipping injection")
        return 0

    payload = read_payload()
    debug(f"payload keys: {list(payload.keys())}")

    prompt = payload.get("prompt") or ""
    if prompt.lstrip().startswith("/"):
        debug("slash command detected, skipping injection")
        return 0

    session = session_name(payload)
    debug(f"session={session}")

    # Try HTTP first, fall back to filesystem
    rendered = fetch_view_http(session)
    if not rendered:
        sd = swarm_dir()
        if not sd.is_dir():
            debug(f"swarm dir does not exist: {sd}")
            return 0
        debug(f"using filesystem: swarm={sd}")
        rendered = render_view_for_session(sd, session)

    if not rendered:
        debug("rendered view is empty, skipping injection")
        return 0

    debug(f"injecting {len(rendered)} bytes of context")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Top-level guard: never block the user's prompt due to a hook bug.
        debug(f"fatal: {e!r}")
        sys.exit(0)
