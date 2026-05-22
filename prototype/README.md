# myco — Daemon and hooks (Python)

Complete implementation of the myco v1 protocol. Daemon, Claude Code hooks, and test suite.

## Components

| File | Description |
|---|---|
| `mycod.py` | Daemon: polling + HTTP server + SwarmIndex + renderer (~1000 lines) |
| `myco-hook.py` | Stop hook: captures `<myco>` blocks → POST /events to the daemon |
| `myco_prompt_hook.py` | UserPromptSubmit hook: injects the view as additionalContext |
| `myco_view.py` | Library + CLI to render views on demand |
| `test_v1.py` | Test suite: **285 unit tests** covering full functionality (+ 5 integration tests in `test_multi_tenant.py` that require a running daemon) |

## Running the daemon

```bash
# Default port 8000; daemon is always multi-channel.
python3 mycod.py /tmp/myco-swarm

# Custom port
python3 mycod.py --port 9000 /tmp/myco-swarm

# Quiet mode (no debug output)
python3 mycod.py -q /tmp/myco-swarm
```

Authentication:
- Every request (except `/healthz`) needs `Authorization: Bearer <token>`.
- The SHA256 of the token identifies the channel; channels are fully isolated.
- Tokens must meet minimum strength requirements (≥ 32 chars, ≥ 80 bits of entropy) at the moment the channel is created.
- Generate a token with `openssl rand -hex 24` or similar.

The daemon:
- Creates a subdirectory per channel in `<swarm_dir>/channels/<sha256>/`
- Inside each channel: `log/`, `view/`, `msg/`
- Runs the HTTP server in a background thread + poll loop on the main thread
- Re-renders views on every detected change
- Rebuilds full state from scratch on restart (stateless — channels are re-read from disk)
- Auto-registers a session on the first `GET /view/<SESSION>`: the session starts existing the moment it asks for its own view, without needing to publish anything first.

## Running the tests

```bash
cd prototype
python3 -m pytest test_v1.py -v
```

285 tests covering:

- Event and key:value parsing
- SwarmIndex (status, needs/provides, blockers, dependents)
- View rendering (worker, DIRECTOR, visibility filters)
- HTTP endpoints (events, view, msg, healthz, status, dispatch)
- Authentication (Bearer token)
- Hybrid mode (HTTP + filesystem coexisting)
- Rich messages (msg/ GET/POST, auto-ack, immutability, size limit)
- Security (tag sanitization, path traversal, self-ask)
- Verbs: say (broadcast), ask/reply, note, direct
- Question TTL (expiry after 30min)
- Last-seen timestamps

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)
- `pytest` for the tests

## How sessions connect

Sessions don't need manual setup. The `myco` launcher (at the repo root) does everything:

```bash
# At the myco repo root
./myco FRONT ~/my-project
```

For manual setup (rare):

```bash
export MYCO_SESSION=FRONT
export MYCO_URL=http://localhost:8000
export MYCO_TOKEN=$(openssl rand -hex 24)  # required
export MYCO_INJECT_VIEW=1
```

> When `MYCO_URL` is set, the hooks treat the HTTP daemon as the single
> source of truth — no fallback to a local swarm. An unreachable daemon
> or rejected token results in "empty view", never in "view mixed with
> another swarm".

## Historical validation files

| File | Description |
|---|---|
| `EXPERIMENT.md` | Injection vs induction experiment (conditions A–F) |
| `RESULTS.md` | Phase 0 validation results (latency, concurrency) |
| `HOOK-VALIDATION.md` | Stop hook validation |
