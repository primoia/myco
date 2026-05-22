# Heterogeneous swarm — Claude × DeepSeek

> Validating that two AI sessions from different providers can be **peers** in the same myco swarm, coordinating through the protocol with no special-casing.

This is a reproducible record of three rounds run on 2026-05-10 between:

- **`CLAUDE-SPEC`** — Anthropic Claude (Opus 4.7, 1M context), spec author + reviewer
- **`DEEPSEEK-IMPL`** — DeepSeek v4-pro, implementer

Both sessions use the standard `claude` CLI. DeepSeek connects via the Anthropic-compatible endpoint by overriding three env vars (see `run-deepseek-impl.sh`). Hooks, daemon, protocol — identical.

## What the experiment shows

1. **The protocol is model-agnostic.** Plain text `<myco>` blocks + an injected panel are all that's required. Any LLM that can follow structured instructions can be a peer.
2. **Cross-vendor coordination works in practice.** Round-trip `ask → reply` (including with `re:` to close pending questions) operated cleanly across providers in three different tasks.
3. **Capability is convergent; discipline isn't.** When given identical specs, the two models produced strikingly similar code (same data structures, same architectures, even similar style). The differences appeared in axes that automated tests don't catch — visual validation, polish, end-user QA.

## The three rounds

| # | Task | CLAUDE-SPEC role | DEEPSEEK-IMPL role | Outcome |
|---|---|---|---|---|
| 1 | `parse_iso8601_duration` (Python) | spec author + reviewer | implementer | Implementer 7/7 green in ~1.5min. Second iteration (edge case `"PT"` empty) fixed in ~2min, 8/8 green. |
| 2 | `LRUCache` (Python) | implementer | implementer | Technical tie: both 9/9 green, both chose `OrderedDict` + `move_to_end`, ~32 LOC each. Cross-reviews almost mirrored. |
| 3 | Tetris (HTML/CSS/JS, 11 tests) | implementer | implementer | Both 11/11 logic tests green. DeepSeek shipped more polished UX (cell size, grid lines, game-over score). Claude shipped with a CSS bug (`[hidden]` HTML attribute defeated by `display: flex` author rule) — overlay was permanently visible. Logic tests didn't catch it; the CLI session couldn't open a browser. |

## What to read

| File | Contents |
|---|---|
| [`scenario-01-spec-impl.md`](scenario-01-spec-impl.md) | The original experiment design + criteria (C1–C6) |
| [`evaluations/claude-perspective.md`](evaluations/claude-perspective.md) | Claude's self-evaluation of the experiment (acknowledged bias as self-evaluator) |
| [`evaluations/deepseek-perspective.md`](evaluations/deepseek-perspective.md) | DeepSeek's independent evaluation |
| [`duel/`](duel/) | Cross-review rubric and challenge framework used in rounds 2 and 3 |
| [`tetris/`](tetris/) | Tetris SPEC + REVIEW-RUBRIC handed to both sessions |

The two evaluation files were written **independently** by the two sessions at the end of the experiment. Reading both gives a stereoscopic view: where they agree (protocol works, capability is convergent), where they diverge (Claude's auto-critique on `done result:ok` overclaim, DeepSeek's critique on "manual orchestration vs autonomous swarm").

## Reproducing

You need:
- A myco daemon reachable from wherever your sessions run
- An Anthropic API key (for the Claude session)
- A DeepSeek API key (for the DeepSeek session)

```bash
# 1. Copy and fill the tenant config
cp tenant.env.example tenant.env
# Edit MYCO_URL and MYCO_TOKEN

# 2. Export the DeepSeek key in the shell that will run the DeepSeek session
export DEEPSEEK_API_KEY=sk-...

# 3. Terminal A: Claude session
bash run-claude-spec.sh

# 4. Terminal B: DeepSeek session
bash run-deepseek-impl.sh
```

Each launcher copies `~/myco/CLAUDE.md` (the protocol instructions) into the session's working directory and starts `claude` with the right backend.

## Honest caveats

These evaluations also surface real issues the team is tracking. From the two perspectives:

**Protocol — incremental refinements wanted:**
- Semantics of `reply` don't fit the "review something the peer closed with `done`" flow. A dedicated review verb, or `reply` accepting a `done` event id, would help.
- No technical enforcement against peeking at `peers/<OTHER>/` before the peer's `done`. Today it relies on discipline of the participating models.

**Daemon — bugs to fix:**
- `GET /msg/<file>?session=` returned empty body (200 with `Content-Length: 0`) in some runs
- Each `<myco>` block produced 2 events in the panel (Stop hook retry suspected)
- `MESSAGES PENDING` did not always clear after read-with-ack

**Experiment design — meta observations:**
- Human routing (instead of fully autonomous swarm) blurred the line between "the protocol is working" and "the human is the messenger". Future rounds should be set up to remove the human from the coordination loop, even at the cost of less control over the schedule.

The protocol team considers these incremental, not structural. The cross-vendor demonstration succeeded — three rounds, both models, zero malformed blocks, zero failed round-trips.
