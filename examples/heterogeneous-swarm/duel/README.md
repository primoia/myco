# Duel — Claude Opus 4.7 (1M) vs DeepSeek v4-pro (1M)

Same challenge, two arenas, simultaneous code, honest cross-review.

## Structure

```
duel/
├── CHALLENGE.md              # challenge spec (LRU cache in Python)
├── tests-shared.py           # 9 official tests — both must pass
├── REVIEW-RUBRIC.md          # 6 evaluation axes for the cross-review
├── run-claude-duel.sh        # launches CLAUDE-DUEL (Claude default)
├── run-deepseek-duel.sh      # launches DEEPSEEK-DUEL (deepseek-v4-pro)
├── claude-arena/             # CLAUDE-DUEL cwd — will contain lru.py
│   └── peers/DEEPSEEK-DUEL/  # symlink → ../../deepseek-arena (for review)
├── deepseek-arena/           # DEEPSEEK-DUEL cwd
│   └── peers/CLAUDE-DUEL/    # symlink → ../../claude-arena
└── observations.md           # duel journal (you create this as you run)
```

## Choreography (3 phases)

### Phase 1 — Simultaneous coding

**Terminal A (CLAUDE-DUEL):**
```
bash run-claude-duel.sh
```

**Terminal B (DEEPSEEK-DUEL):**
```
export DEEPSEEK_API_KEY=sk-...    # if not exported yet
bash run-deepseek-duel.sh
```

Once both are up, **paste exactly the same prompt into both at roughly the same time**:

> You are in an implementation duel. Read `CHALLENGE.md` and implement per spec. Copy `tests-shared.py` into your cwd and run pytest until 9/9 green. When green, post `done lru-cache result:ok ref:lru.py`. **Do NOT read `peers/<OTHER>/lru.py` before your done — you are being evaluated on independence.** The peer is doing the same challenge in parallel.

Both will work in parallel. The panel shows `start lru-cache` on both sides — they know they are racing each other.

### Phase 2 — Honest cross-review

When both post `done`, give each a minimal trigger turn (any nudge, e.g. `revise`):

> The peer finished. Read `REVIEW-RUBRIC.md`, then `peers/<OTHER>/lru.py` (and `peers/<OTHER>/test_lru.py` if present). Do the structured review per the rubric. Post as `reply <OTHER>` with `re:` pointing at the peer's `done` and `spec:` pointing at your `msg/REVIEW-<YOU>-001.md` (short form — msg inline). Be honest: call out bugs, comment on design, identify what you would copy and what you wouldn't.

### Phase 3 — Final comparison

You (the human) read both reviews + both `lru.py`. Decide what you learned. Record in `observations.md`.

## Metrics the swarm collects automatically

- **Time-to-done** — timestamp delta between `start lru-cache` and `done lru-cache` on each side
- **Iterations-to-green** — how many times each ran pytest before posting done (visible in panel events if each posts `start <attempt>`, or in shell Bash history)
- **Lint warnings** — any `warnings:` in the POST /events response
- **Review contents** — text of `msg/REVIEW-*.md`

## Metrics you (human) collect by hand

- **Token cost × price.** Each CLI shows API usage — note an estimate
- **LoC of `lru.py`** on each side
- **"Caught the other's bug" rate** — compare what each review flagged vs. what was real
- **Aesthetic call.** Subjective but worth it: which code would you keep in your own project?

## What this experiment is calibrated to show

| question | where it shows up |
|---|---|
| Comparable execution speed? | time-to-done |
| Convergence: who goes green with fewer iterations? | logs / bash history |
| Honest critique: do they find the other's bugs? | reviews |
| Calibrated critique: do they flag false positives? | compare reviews × code |
| Self-awareness: does each acknowledge its own trade-offs? | section "C5 — design taste" of the review |

## Pre-flight check

Daemon alive:
```
curl -sS http://YOUR-DAEMON-HOST:8000/healthz
```

Tenant configured:
```
source ../tenant.env && echo $MYCO_URL && echo "${MYCO_TOKEN:0:20}..."
```

DeepSeek key available (in Terminal B before launching):
```
echo "${DEEPSEEK_API_KEY:?not exported}"
```

`peers/` symlinks in place (create after first launch if missing):
```
ls -la claude-arena/peers deepseek-arena/peers
```

All green? Go.
