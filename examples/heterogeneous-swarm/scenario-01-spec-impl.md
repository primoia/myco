# Scenario 01 — Spec → Implement (Claude vs DeepSeek)

## Goal of the experiment

Validate that a DeepSeek session can act as a valid peer in a myco swarm coordinated with Claude. We are **not** evaluating "who implements better" — we are validating the **communication contract**: the DeepSeek session emits well-formed `<myco>` blocks, reads the injected panel, and performs a clean `ask → reply` round-trip without breaking coordination.

## Sessions and roles

| session | engine | cwd | role |
|---|---|---|---|
| CLAUDE-SPEC | Claude (default) | `./spec/` | spec author; reviewer; final arbiter |
| DEEPSEEK-IMPL | DeepSeek v4-pro | `./impl/` | spec implementer |

(`./spec/` and `./impl/` are created relative to this example directory by the launcher scripts.)

## Proposed contract (CLAUDE-SPEC will post this in `msg/SPEC-001.md`)

> Implement `parse_iso8601_duration(s: str) -> int` in pure Python. Returns the duration in seconds as an `int`.
>
> Accepted format: subset of ISO 8601 §4.4.4.2 with time components (`PnYnMnDTnHnMnS`). Integers only — no fractional values, no weeks (`P1W`), no negative years, no timezone.
>
> Fixed conversions: `Y` = 365 days, `M` = 30 days, `D` = 86400, `H` = 3600, `M` (after T) = 60, `S` = 1.
>
> **Errors:** raise `ValueError` for any string outside the format.
>
> **Mandatory test cases:**
> - `parse_iso8601_duration("PT1H30M5S") == 5405`
> - `parse_iso8601_duration("P1DT2H") == 93600`
> - `parse_iso8601_duration("PT0S") == 0`
> - `parse_iso8601_duration("P")` → ValueError
> - `parse_iso8601_duration("1H")` → ValueError (missing `P`)
> - `parse_iso8601_duration("P1W")` → ValueError (no week support)
> - `parse_iso8601_duration("PT1.5H")` → ValueError (no fractional)
>
> **Deliverable:** `parse_duration.py` + `test_parse_duration.py` in the implementer's directory. `python3 -m pytest test_parse_duration.py -q` must pass green.

## Expected flow (round-trip)

```
CLAUDE-SPEC                    DEEPSEEK-IMPL
     │                              │
     │ POST /events with msgs inline│
     │  ask DEEPSEEK-IMPL impl-iso  │
     │  spec:msg/SPEC-001.md        │
     ├─────────────────────────────►│
     │                              │
     │                              │ (reads panel, sees pending msg)
     │                              │ curl /msg/SPEC-001.md
     │                              │ implements in impl/
     │                              │
     │                              │ reply CLAUDE-SPEC done
     │                              │   re:msg/SPEC-001.md
     │                              │   ref:impl/parse_duration.py
     │                              │   result:ok
     │◄─────────────────────────────┤
     │                              │
     │ (reviews via peers/IMPL/)    │
     │ if ok: done                  │
     │ if not: ask again            │
     ▼                              ▼
```

## Evaluation criteria (what to measure and where)

| criterion | where to measure | answer |
|---|---|---|
| C1 — DEEPSEEK-IMPL emits valid `<myco>` | daemon logs (`mycod` in verbose) and CLAUDE-SPEC's panel | does `DEEPSEEK-IMPL: ask/reply/done ...` appear? |
| C2 — Lint emits warnings | JSON response of POST /events | does `warnings: [...]` appear when IMPL misuses a verb? |
| C3 — `re:` closes the question | `## PENDING QUESTIONS` in CLAUDE-SPEC's view | does the ask leave the list after the reply? |
| C4 — DEEPSEEK reads msg via curl | daemon logs | does `GET /msg/SPEC-001.md?session=DEEPSEEK-IMPL` show up? |
| C5 — implementation is correct | `pytest test_parse_duration.py` | does it pass green? |
| C6 — Round-trip time | timestamps in the panel | minutes between ask and reply |

## Possible friction points (record in your own notes if they occur)

- Malformed `<myco>` block (wrapped in ```` ```fences ```` `, invalid verb, etc.)
- Tool use stuck (Edit/Write failing because the Anthropic→DeepSeek adapter lost nuance)
- DEEPSEEK session can't curl the daemon (firewall? wrong token?)
- DEEPSEEK session ignores lint warnings
- Quality variance between rounds

## How to run

1. **Bring up both sessions in separate terminals:**
   ```
   bash run-claude-spec.sh
   ```
   ```
   export DEEPSEEK_API_KEY=sk-...
   bash run-deepseek-impl.sh
   ```

2. **Start in CLAUDE-SPEC.** Paste this prompt:

   > Your mission: write the contract into `msg/SPEC-001.md` exactly as described in `scenario-01-spec-impl.md` (section "Proposed contract"). Use the short form of POST /events (msgs inline + `ask DEEPSEEK-IMPL impl-iso-duration spec:msg/SPEC-001.md`). Wait for the reply, review the code produced by DEEPSEEK-IMPL via `peers/IMPL/`, and finish with `done impl-iso-duration result:ok` (or ask again if the implementation fails the tests).

3. **Don't give any instruction to DEEPSEEK-IMPL initially.** It should discover everything from the panel:
   - See the pending message under PENDING MESSAGES
   - Read it via curl
   - Implement
   - Post reply

4. **Periodically screenshot or copy the panel** into your notes file. The panel is the auditable fact.

## Iteration plan

If C1 and C2 pass but the implementation fails → the protocol is OK, the model needs a tighter prompt. Re-run with a more specific prompt for DEEPSEEK-IMPL.

If C1 fails (malformed block) → add a stronger anchor in the session-specific `CLAUDE.md`.

If C3 fails → daemon bug (likely already fixed in `protocol-wins` branch, but confirm).

If everything passes → run scenario 02 with reversed roles (DeepSeek writes spec, Claude implements).
