#!/usr/bin/env python3
"""
myco_view.py — render a myco view on demand.

Library-first: the main entry point is `render_view_for_session`, which
builds a fresh SwarmIndex from the swarm's log directory and returns the
rendered markdown view as a string. This is imported by the
UserPromptSubmit hook (prototype/myco_prompt_hook.py) and can also be run
as a CLI for manual debugging:

    python3 myco_view.py <swarm_dir> <session>

The CLI output is bit-identical to what the hook would inject.

This module has no side effects at import time. It reuses SwarmIndex,
parse_event and render_view from mycod.py via direct import.
"""

import sys
from pathlib import Path

from mycod import SwarmIndex, parse_event, render_view


def render_view_for_session(swarm_dir: Path, session: str) -> str:
    """Build a fresh SwarmIndex from swarm_dir/log/*.log and render the
    view for `session`. Returns the rendered markdown as a string.

    Returns "" if swarm_dir or swarm_dir/log does not exist, or if the
    log directory is empty of log files. Any other error propagates.
    """
    swarm_dir = Path(swarm_dir)
    log_dir = swarm_dir / "log"
    if not log_dir.is_dir():
        return ""

    log_files = sorted(log_dir.glob("*.log"))
    if not log_files:
        return ""

    index = SwarmIndex()
    for log_file in log_files:
        sess = log_file.stem
        try:
            text = log_file.read_text(errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            ev = parse_event(sess, line)
            if ev is not None:
                index.apply(ev)

    # Ensure the target session is known even if it has no events yet,
    # so render_view produces a non-empty view with status "unknown".
    index.sessions_known.add(session)

    return render_view(index, session)


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: myco_view.py <swarm_dir> <session>", file=sys.stderr)
        return 2
    swarm_dir = Path(sys.argv[1])
    session = sys.argv[2]
    out = render_view_for_session(swarm_dir, session)
    if not out:
        return 0
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
