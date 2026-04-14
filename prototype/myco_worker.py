#!/usr/bin/env python3
"""
myco-worker — persistent worker daemon for a Claude session.

Watches $MYCO_SWARM/dispatch/SESSION.prompt for incoming prompts.
When a prompt arrives, feeds it to `claude --resume <session-id> -p "prompt"`.
The session persists between dispatches: Claude keeps full conversation context.
Myco hooks fire normally (view injected, <myco> blocks captured).

Usage:
    myco-worker <session> <project_dir> [--swarm <swarm_dir>] [--model <model>]

Example:
    myco-worker AUTH /mnt/ramdisk/teste1
    myco-worker CART /mnt/ramdisk/teste2 --swarm /mnt/ramdisk/myco

The worker:
1. Creates a Claude session on first dispatch (stores session ID)
2. Resumes the session on subsequent dispatches via --resume
3. Saves responses to responses/SESSION-NNN.md
4. Loops until killed

The project_dir must have:
  - .git/           (so Claude Code trusts it)
  - .claude/settings.json  (with hooks configured)
  - CLAUDE.md       (session instructions)

Environment:
    MYCO_SWARM      swarm directory (default: /mnt/ramdisk/myco)
    MYCO_HOOK_DEBUG if set, hooks emit debug info to stderr
"""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path


POLL_INTERVAL = 0.5  # seconds


class Worker:
    def __init__(self, session: str, project_dir: Path, swarm_dir: Path,
                 model: str | None = None):
        self.session = session
        self.project_dir = project_dir.resolve()
        self.swarm_dir = swarm_dir.resolve()
        self.dispatch_dir = self.swarm_dir / "dispatch"
        self.responses_dir = self.swarm_dir / "responses"
        self.sessions_dir = self.swarm_dir / "sessions"
        self.prompt_file = self.dispatch_dir / f"{session}.prompt"
        self.session_id_file = self.sessions_dir / f"{session}.id"
        self.dispatch_count = 0
        self.model = model

        # Deterministic UUID from session name (stable across restarts)
        self.session_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"myco-{session}"))

        # Ensure dirs exist
        for d in (self.dispatch_dir, self.responses_dir, self.sessions_dir):
            d.mkdir(parents=True, exist_ok=True)

        # Track whether session has been initialized
        self.initialized = self.session_id_file.exists()

    def _log(self, msg: str):
        now = time.strftime("%H:%M:%S")
        print(f"[myco-worker {now}] {self.session}: {msg}", file=sys.stderr)

    def _env(self) -> dict:
        env = os.environ.copy()
        env["MYCO_SESSION"] = self.session
        env["MYCO_INJECT_VIEW"] = "1"
        env["MYCO_SWARM"] = str(self.swarm_dir)
        return env

    def _build_cmd(self, prompt: str) -> list[str]:
        """Build the claude CLI command."""
        cmd = ["claude"]

        if self.initialized:
            # Resume existing session
            cmd.extend(["--resume", self.session_id])
        else:
            # First run: create session with specific ID
            cmd.extend(["--session-id", self.session_id])

        cmd.extend(["-p", prompt])
        cmd.extend(["--output-format", "json"])

        if self.model:
            cmd.extend(["--model", self.model])

        return cmd

    def _run_claude(self, prompt: str) -> dict | None:
        """Run claude with the given prompt, return parsed JSON result or None."""
        cmd = self._build_cmd(prompt)
        self._log(f"cmd: {' '.join(cmd[:6])}...")
        self._log(f"prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=self._env(),
                cwd=str(self.project_dir),
                timeout=600,  # 10 min max per dispatch
            )
        except subprocess.TimeoutExpired:
            self._log("TIMEOUT after 600s")
            return None

        if proc.stderr:
            for line in proc.stderr.strip().split("\n")[:5]:
                self._log(f"  stderr: {line}")

        if proc.returncode != 0:
            self._log(f"claude exited with code {proc.returncode}")
            return None

        # Mark session as initialized after first successful run
        if not self.initialized:
            self.session_id_file.write_text(self.session_id)
            self.initialized = True
            self._log(f"session created: {self.session_id}")

        # Parse JSON output
        if proc.stdout:
            try:
                result = json.loads(proc.stdout)
                # Update session_id if returned (might differ from ours)
                if "session_id" in result:
                    actual_id = result["session_id"]
                    if actual_id != self.session_id:
                        self._log(f"session_id updated: {actual_id}")
                        self.session_id = actual_id
                        self.session_id_file.write_text(actual_id)
                return result
            except json.JSONDecodeError:
                return {"result": proc.stdout, "is_error": False}
        return None

    def _save_response(self, prompt: str, result: dict):
        """Save the dispatch response for DIRECTOR to review."""
        self.dispatch_count += 1
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{self.session}-{ts}-{self.dispatch_count:03d}.md"
        response_text = result.get("result", "(no response)")
        cost = result.get("cost_usd", "?")
        turns = result.get("num_turns", "?")

        content = (
            f"# {self.session} dispatch #{self.dispatch_count}\n\n"
            f"**Prompt:** {prompt}\n\n"
            f"**Cost:** ${cost} | **Turns:** {turns}\n\n"
            f"**Response:**\n\n{response_text}\n"
        )
        (self.responses_dir / filename).write_text(content)
        self._log(f"saved: responses/{filename} (cost=${cost}, turns={turns})")

    def dispatch(self, prompt: str):
        """Send a prompt to the Claude session and save the response."""
        result = self._run_claude(prompt)
        if result:
            self._save_response(prompt, result)
        else:
            self._log("no result from claude")

    def poll_once(self) -> bool:
        """Check for a dispatch prompt. Returns True if one was processed."""
        if not self.prompt_file.exists():
            return False
        try:
            prompt = self.prompt_file.read_text().strip()
            self.prompt_file.unlink()
        except (OSError, FileNotFoundError):
            return False
        if not prompt:
            return False
        self._log(f"picked up dispatch: {prompt[:80]}")
        self.dispatch(prompt)
        return True

    def run(self):
        """Main loop: poll for dispatches."""
        self._log(f"starting (project={self.project_dir}, swarm={self.swarm_dir})")
        self._log(f"session_id={self.session_id} (initialized={self.initialized})")
        self._log(f"watching {self.prompt_file}")

        try:
            while True:
                self.poll_once()
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            self._log("stopped")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="myco worker daemon")
    parser.add_argument("session", help="Session name (e.g. AUTH, CART)")
    parser.add_argument("project_dir", help="Working directory for the session")
    parser.add_argument("--swarm", default=None,
                        help="Swarm directory (default: $MYCO_SWARM or /mnt/ramdisk/myco)")
    parser.add_argument("--model", default=None,
                        help="Model to use (e.g. sonnet, opus)")
    args = parser.parse_args()

    swarm_dir = (Path(args.swarm) if args.swarm
                 else Path(os.environ.get("MYCO_SWARM", "/mnt/ramdisk/myco")))
    Worker(
        session=args.session,
        project_dir=Path(args.project_dir),
        swarm_dir=swarm_dir,
        model=args.model,
    ).run()


if __name__ == "__main__":
    main()
