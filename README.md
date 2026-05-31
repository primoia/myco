# myco

[![PyPI](https://img.shields.io/pypi/v/primoia-myco.svg)](https://pypi.org/project/primoia-myco/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![tests](https://github.com/primoia/myco/actions/workflows/tests.yml/badge.svg)](https://github.com/primoia/myco/actions/workflows/tests.yml)
[![Status](https://img.shields.io/badge/status-v1.1_stable-green.svg)](docs/PROTOCOL.md)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](pyproject.toml)

🇧🇷 [Leia em português](README.pt-BR.md)

<!-- 
  TODO: drop docs/demo.gif here once recorded — see docs/RECORD-DEMO-GIF.md
  <p align="center">
    <img src="docs/demo.gif" alt="myco demo: ALICE asks BOB through the swarm bus" width="800">
  </p>
-->

**Problem:** running multiple Claude Code sessions in parallel produces conflicts, repeated work, and stale assumptions — the agents have no shared awareness.

**myco** is a text-only coordination protocol + tiny Python daemon that gives N parallel agent sessions a shared, filtered view of each other's actions. No central orchestrator. No tool calls. Vendor-agnostic (Claude, DeepSeek, anything Anthropic-compatible).

> The name comes from the mycelium: an underground fungal network that connects independent trees, silently transporting signals between them.

## Why

If you use Claude Code (or any agent CLI) intensively, you've probably hit the wall:

- **Long sessions degrade attention.** Even with a 1M context window, late-conversation precision drops.
- **One thread can't hold everything.** Refactoring the backend while debugging the frontend while reviewing docs = chaos in a single chat.
- **Parallel tabs without coordination are worse.** Three agents editing the same repo with no shared awareness produces conflicts, repeated work, and stale assumptions.

myco lets you run **N persistent sessions in parallel**, each with its own role and clean context, sharing only what matters through a silent bus.

## Comparison with alternatives

myco occupies a niche that the big agent frameworks don't address: **human-in-the-loop coordination of N persistent agent sessions across providers, with no central orchestrator**.

| | myco | LangGraph / CrewAI / AutoGen | tmux / tmuxinator | Multiple chat tabs |
|---|---|---|---|---|
| **Coordination model** | Human routes, agents publish to shared bus | Code-driven orchestrator | None — just layout | None |
| **Persistence across days** | ✅ via `--resume` + daemon ledger | ❌ runs are stateless by default | ❌ layout only | ❌ tab dies, history goes |
| **Multi-provider in one swarm** | ✅ Claude + DeepSeek + … | Possible but requires per-framework adapters | N/A | N/A |
| **Cross-machine** | ✅ HTTP daemon, sessions on any VM | ❌ in-process | ❌ local only | ❌ |
| **Built-in protocol lint** | ✅ daemon warns on common mistakes | ❌ | N/A | N/A |
| **Code overhead per project** | None — hooks read/write text | High — define graphs, tools, state | Low — yaml layout | Zero |
| **Best for** | Devs running 5–10 long-lived sessions | Autonomous agent loops with no human | Window/pane management | Casual single-session use |

In short: if you're already pasting copy-paste between Claude tabs to keep them in sync, myco replaces the copy-paste with a silent bus. If you wanted a fully autonomous multi-agent loop with no human, use LangGraph/CrewAI/AutoGen instead — they're built for that and myco is not.

## Multi-provider (Claude × DeepSeek × anything Anthropic-compatible)

The myco protocol is plain text (`<myco>` block in the response + panel injected in the prompt). **Any model that can follow structured instructions can participate**, regardless of vendor.

In practice, this works by pointing the Claude Code CLI at any Anthropic-compatible endpoint:

```bash
# DeepSeek session in the same swarm
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"
export ANTHROPIC_MODEL="deepseek-v4-pro"
./myco DEEPSEEK-IMPL ~/my-project
```

Validated experimentally across **3 rounds** with both sessions writing independent self-evaluations afterwards. Full record (scripts, rubrics, both perspectives) in [`examples/heterogeneous-swarm/`](examples/heterogeneous-swarm/):

- **Round 1 (Spec → Impl):** Claude writes the contract, DeepSeek implements in ~1.5min (7/7 tests). Claude finds an edge case, DeepSeek fixes in ~2min (8/8). Clean round-trip via `msg/` + `ask` + `reply`.
- **Round 2 (LRUCache, parallel):** Technical tie. Both 9/9 green, both `OrderedDict` + `move_to_end`, ~32 LOC each. Cross-reviews nearly mirrored.
- **Round 3 (Tetris, parallel):** Both 11/11 logic tests green. DeepSeek shipped more polished UX (larger canvas, grid lines, score on game-over). Claude shipped with `[hidden]` HTML attribute defeated by `display: flex` in its own CSS — overlay permanently visible. Tests passed; the game didn't.

The deciding axis wasn't capability — it was **discipline at non-tested validation**. Capability converged (same idioms, same architectures). The CLI session is blind to UI, and that affects whatever model sits behind it.

Practical implications:
- **Cost mix** — single Opus architect + several cheap DeepSeek/Groq implementers per round
- **Capability mix** — right model per role (design vs bulk code vs review)
- **Resilience** — one provider has an outage, the swarm keeps moving
- **No vendor lock-in** — the protocol doesn't care who's behind any session

## Install

Works on macOS and Linux. Requires **Python 3.8+** and the Claude Code CLI (for the launcher).

```bash
# Check Python version (must be 3.8 or newer)
python3 --version

# Install from PyPI — installs `mycod`, `myco-view`, `myco-hook`,
# `myco-prompt-hook` as commands on your PATH. Stdlib-only, zero deps.
pip install primoia-myco
```

That's it. No system packages, no openssl required, no compilation. Token generation uses Python's stdlib (see below).

## Two sessions chatting in 60 seconds

This is the minimal "is it real" demo. You'll run a daemon and two Claude Code sessions that pass a question back and forth through the myco bus.

```bash
# ── Terminal 1: daemon ───────────────────────────────────────────────
pip install primoia-myco
mkdir -p /tmp/myco-demo
mycod --port 8000 /tmp/myco-demo
```

```bash
# ── Terminal 2: launcher repo (one-time, for the bash launcher script) ─
git clone --depth=1 https://github.com/primoia/myco.git ~/myco-launcher
cd ~/myco-launcher

# Generate a random tenant token — stdlib only, no openssl needed
export MYCO_URL=http://localhost:8000
export MYCO_TOKEN="myco-$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

# Start session ALICE (in a fresh empty workdir)
mkdir -p /tmp/alice && ./myco ALICE /tmp/alice
```

```bash
# ── Terminal 3: second session, same MYCO_URL + MYCO_TOKEN ──────────
cd ~/myco-launcher
export MYCO_URL=http://localhost:8000
export MYCO_TOKEN="$( ... paste the same token from Terminal 2 ... )"

mkdir -p /tmp/bob && ./myco BOB /tmp/bob
```

Now in Terminal 2 (ALICE), tell Claude:
> *Ask BOB which JWT library we should use. Wait for the reply.*

ALICE will emit `<myco>ask BOB which-jwt-library</myco>`, which the daemon delivers to BOB's panel on its next prompt. BOB will see the pending question, answer with `<myco>reply ALICE use-jose-v5</myco>`, and ALICE's next prompt will show the answer in its panel — no copy-paste, no shared file, no manual relay.

Want a richer scenario? See [`examples/heterogeneous-swarm/`](examples/heterogeneous-swarm/) for the Claude × DeepSeek experiment with 3 rounds and independent self-evaluations.

## How it works

1. **Sessions log via `<myco>` blocks** — Claude writes a block at the end of each response; a Stop hook captures it and sends it to the daemon
2. **Daemon indexes and renders views** — keeps state in memory and generates a personalized markdown view per session
3. **Views are injected automatically** — a UserPromptSubmit hook injects the view as additional context on each prompt, with no tool calls

```
┌─────────────┐     <myco> block      ┌──────────┐    view/{S}.md     ┌─────────────┐
│  Session A  │ ──── Stop hook ────▶  │  mycod   │ ── Prompt hook ──▶ │  Session B  │
│  (Claude)   │                       │ (daemon) │                    │  (Claude)   │
└─────────────┘                       └──────────┘                    └─────────────┘
```

## The `myco` launcher

The `myco` script in the repo root automates the full session setup:

```bash
./myco <SESSION> [project_dir] [--resume] [-- claude_flags...]

# Examples
./myco FRONT ~/my-project              # FRONT session in the my-project repo
./myco FRONT ~/my-project --resume     # resume previous session
./myco FRONT . -- --model sonnet       # extra flags forwarded to claude
```

What it does:
- Copies `CLAUDE.md` (the protocol instructions) into the target project
- Creates `.claude/settings.json` with the hooks configured
- Exports `MYCO_SESSION`, `MYCO_URL`, `MYCO_INJECT_VIEW`
- Runs `claude` in the project directory

## Protocol

**12 verbs** for coordination (`private` is the canonical "private note" verb; `log` and `note` are legacy aliases of it):

| Verb | Meaning |
|---|---|
| `start` | I started working on X |
| `done` | I finished X (supports `ref:`, `spec:`, `result:`) |
| `need` | I declare a dependency on X |
| `block` | I'm blocked |
| `up` | a resource came up (supports `addr:`) |
| `down` | a resource went down |
| `ask` | targeted question to another session |
| `reply` | answer to a question |
| `say` | broadcast visible to all sessions |
| `direct` | directive (DIRECTOR-only) |
| `private` | private note (invisible to others) |
| `log` / `note` | legacy aliases of `private` |

**key:value conventions**: `ref:origin/feat/login`, `spec:msg/AUTH-001.md`, `ack:msg/CART-001.md`, `addr:http://host:port`, `result:ok|fail|partial`, `re:msg/ID.md`

**Rich messages**: markdown files exchanged via HTTP under `msg/`, referenced with `spec:`.

Full details in [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## HTTP transport

The daemon exposes an HTTP API for cross-VM use:

| Endpoint | Method | Description |
|---|---|---|
| `/healthz` | GET | Health check (no auth) |
| `/view/{SESSION}` | GET | Rendered view for the session |
| `/events` | POST | Event ingestion |
| `/msg/{FILE}` | GET | Message read (`?session=` auto-acks) |
| `/msg/{FILE}` | POST | Message create (immutable, max 64KB) |
| `/status` | GET | JSON state of all sessions |

**Auth**: Bearer token via `MYCO_TOKEN` (all routes except `/healthz`).

**Security**: sanitization of dangerous tags in `msg/`, message immutability (409 on overwrite), 64KB limit, path-traversal protection.

## Documents

- [`docs/CONCEPT.md`](docs/CONCEPT.md) — the full idea, principles, reasoning
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — v1 protocol specification
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — daemon and hooks architecture
- [`prototype/`](prototype/) — daemon, hooks, tests (296 unit tests passing)
- [`examples/three-services/`](examples/three-services/) — example with SN + SM + IAM
- [`swarm/`](swarm/) — `CLAUDE.md` templates for sessions and DIRECTOR

## Cross-VM setup

```bash
# Remote VM
git clone https://github.com/primoia/myco.git
export MYCO_URL=http://<daemon-ip>:8000
export MYCO_TOKEN=your-secret-token
cd myco
./myco FRONT ~/remote-project
```

The daemon runs on a central machine. Sessions on any VM point `MYCO_URL` to it.

## Status

**v1.1** — Stable protocol, validated with real sessions across distributed VMs. 296 unit tests passing.

See [`CHANGELOG.md`](CHANGELOG.md) for the version history.

## Known limitations

- **Session instructions in Portuguese.** The launcher copies `CLAUDE.md` (in Portuguese) into each session's project directory. Sessions read it on every prompt to learn the protocol. An English version of this file is on the roadmap — until then, sessions started by the launcher will operate with Portuguese protocol instructions (which all current LLMs handle fine, but is awkward for non-PT contributors reading the source). Workaround: edit `CLAUDE.md` after `./myco` runs, or maintain your own English copy and point the launcher at it.
- **Hooks are Claude Code specific.** The wire protocol (events, views, msg/) is plain HTTP and works with anything. The hook contract (Stop/UserPromptSubmit) is currently Claude Code's. Adapters for Aider, Codex, Continue, etc. are glue work — contributions welcome.
- **Daemon bugs catalogued.** A few non-blocking daemon issues are documented in [`examples/heterogeneous-swarm/evaluations/`](examples/heterogeneous-swarm/evaluations/) (the empty `msg/?session=` response, duplicate events, pending-messages not clearing on ack). Fixes pending.

## License

MIT
