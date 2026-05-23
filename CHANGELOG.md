# Changelog

All notable changes to myco.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [v0.1.1] — anonymized author + private alias bug fix

### Changed
- Package author + maintainer in `pyproject.toml` changed from "Cezar Fuhr" to "Primoia" — aligns with the project being a small dev shop rather than tied to a single developer.
- `LICENSE` copyright holder changed from "Cezar Fuhr" to "Primoia" for the same reason.

### Fixed
- `prototype/myco_hook.py` backward-compat symlink `prototype/myco-hook.py` retained so sessions configured before the rename keep working.

## [Unreleased]

### Added
- **README polished for HN audience.** New TL;DR "Problem/myco is" at the top (2-line scanner version, with the mycelium metaphor demoted to a blockquote below it). New "Comparison with alternatives" section (vs LangGraph/CrewAI/AutoGen, tmux, chat tabs) that anticipates the predictable "but why not X?" thread questions. New "Two sessions chatting in 60 seconds" minimal runnable demo using `pip install` + `python3 -c 'import secrets'` (no openssl required). Explicit Python version check at install. Placeholder block for `docs/demo.gif` hero image with full recording recipe at [`docs/RECORD-DEMO-GIF.md`](docs/RECORD-DEMO-GIF.md) (vhs script + asciinema fallback).
- All relative README links audited (13/13 resolve correctly).
- Tests badge now links to `prototype/README.md` (which documents the suite) instead of the raw test file.

## [v0.1.0 — PyPI] — 2026-05-21

### Added
- **First PyPI release as [`primoia-myco`](https://pypi.org/project/primoia-myco/).** `pip install primoia-myco` installs `mycod`, `myco-view`, `myco-hook`, and `myco-prompt-hook` as commands on the PATH. README documents two install paths: pip-install (commands only) and git-clone (full launcher with auto-setup). The package name uses the `primoia-` org prefix because `myco-swarm` and `mycoswarm` were rejected by PyPI's typo-squatting heuristic against the existing unrelated `myco` package (mycology library).
- `mycod -h` / `mycod --help` (was missing — argparser only knew `--port` and `--quiet`)
- English README (`README.md`); Portuguese version preserved as `README.pt-BR.md`
- `examples/heterogeneous-swarm/` — Claude × DeepSeek experiment record (3 rounds, both sides' independent self-evaluations, scripts, rubrics, test suites)
- `LICENSE` file (MIT) — previously only mentioned in README
- `CHANGELOG.md` (this file)
- Badges in README (license, tests, status, Python version)
- "Known limitations" section in README being honest about Portuguese session templates, Claude-Code-specific hooks, and catalogued daemon bugs

### Changed
- Verb count in README clarified: **12 verbs** total, where `private` is canonical and `log` / `note` are legacy aliases of `private` (the daemon treats all three as synonyms; the hook now recognizes all three after the bug fix above)
- Test count synced to actual (285 unit tests passing in `test_v1.py`, +5 integration tests in `test_multi_tenant.py` that require a running daemon)

### Changed
- Renamed `prototype/myco-hook.py` → `prototype/myco_hook.py` (Python module names can't contain hyphens; required for the package). The bash launcher was updated to reference the new path.

### Fixed
- **Hook now recognizes `private` verb.** `prototype/myco-hook.py` had `VALID_VERBS` containing `log` and `note` but not `private` — sessions emitting `<myco>private foo</myco>` had the event silently dropped before reaching the daemon, despite `private` being documented as the canonical name since v1.6. The daemon already treated all three as synonyms; the hook's set was just stale.
- Sub-READMEs (`duel/`, `tetris/`) translated to English and references to private paths (`~/myco-ds-test/`) replaced with example-relative paths
- LAN IP addresses in demo READMEs replaced with `YOUR-DAEMON-HOST` placeholder

## [v1.1] — 2026-05-09

### Added
- Auto-lint of common protocol mistakes (`reply` with no pending ask, `private` while asks pending) returned in the POST `/events` JSON response
- Short-form msg ingestion: `msgs:` inline in POST `/events` creates the file and posts the referencing event in a single round-trip
- Multi-tenant isolation via SHA256 of bearer token (channels fully isolated)
- Cross-VM transport tested in production-like setups

### Changed
- Protocol corrobated by 5 real sessions feedback ("protocol-wins" branch merged)

### Fixed
- Several daemon bugs around event indexing and view rendering

## [v1.0] — 2026-04-16

### Added
- Initial public release
- Python daemon (`mycod.py`) with in-memory state and file-backed channels
- Stop hook (`myco-hook.py`) and UserPromptSubmit hook (`myco_prompt_hook.py`) for Claude Code
- 11 verbs: `start`, `done`, `need`, `block`, `up`, `down`, `ask`, `reply`, `say`, `direct`, `private`
- Key:value tag conventions (`ref:`, `spec:`, `result:`, `addr:`, `re:`)
- Rich messages via `msg/` files exchanged over HTTP
- `myco` launcher script that wires Claude Code hooks and starts a session
- `examples/three-services/` — three coordinated services (IAM, SM, SN)
- Documentation: `CONCEPT.md`, `PROTOCOL.md`, `ARCHITECTURE.md`, `VISION.md`, `MULTI-TENANT.md`
