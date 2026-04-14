#!/usr/bin/env python3
"""
myco-dispatch — send a prompt to a worker session.

Writes a prompt file to $MYCO_SWARM/dispatch/SESSION.prompt.
The myco-worker daemon for that session picks it up and feeds it
to `claude --resume`.

Usage:
    myco-dispatch <session> <prompt>
    myco-dispatch AUTH "Implementa JWT no login endpoint"

Can also be called from a DIRECTOR Claude session via Bash tool.
"""

import os
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print("usage: myco-dispatch <session> <prompt>", file=sys.stderr)
        sys.exit(2)

    session = sys.argv[1]
    prompt = " ".join(sys.argv[2:])
    swarm_dir = Path(os.environ.get("MYCO_SWARM", "/mnt/ramdisk/myco"))
    dispatch_dir = swarm_dir / "dispatch"
    dispatch_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = dispatch_dir / f"{session}.prompt"
    prompt_file.write_text(prompt)
    print(f"[myco-dispatch] → {session}: {prompt[:80]}{'...' if len(prompt) > 80 else ''}", file=sys.stderr)


if __name__ == "__main__":
    main()
