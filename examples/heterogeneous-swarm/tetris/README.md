# Tetris duel — Claude Opus 4.7 vs DeepSeek v4-pro

Round 3 of the experiment. Tougher than the LRU cache: a full browser game with testable logic, working UI, expected ~400–600 LoC.

## Who plays

Same two sessions from the LRU round. The launchers in the parent example directory already created their arenas:

- **CLAUDE-SPEC** in `../spec/` — Claude Opus 4.7 (1M)
- **DEEPSEEK-IMPL** in `../impl/` — DeepSeek v4-pro

Same tenant. Both sessions see each other in the panel.

## Phase 1 — Simultaneous implementation

Paste **identical text into both** terminals (at roughly the same time):

> You are in a Tetris implementation duel — playable in the browser, with testable logic. Read `tetris/SPEC.md` (full) and `tetris/tests-shared.test.mjs` (the mechanical suite).
>
> Implement in your current arena (`spec/` if you are CLAUDE-SPEC, `impl/` if you are DEEPSEEK-IMPL). The files from the LRU round can stay — they don't interfere. Create the new files the spec requires: `index.html`, `game.mjs`, `ui.mjs`, `style.css` (optional). Copy `tetris/tests-shared.test.mjs` into your arena (don't modify the suite).
>
> Run `node --test tests-shared.test.mjs` repeatedly until the 10 mandatory tests pass. The bonus (Tetris scoring) is desirable but not required.
>
> When complete, post:
> ```
> done tetris-complete result:ok ref:game.mjs
> ```
> If you run out of time (~90min), post:
> ```
> done tetris-partial result:partial ref:game.mjs
> ```
> with a note about what blocked you.
>
> **Do NOT read `peers/<OTHER>/`** before your done. You're evaluated on independence. The peer is doing the same challenge in parallel.

## Phase 2 — Cross-review

When both post `done`, paste into both (any minimal trigger — they'll see the peer's `done` in the panel):

> The peer finished (or stopped). Time for the honest review. Read `tetris/REVIEW-RUBRIC.md` (7 axes, reply format). Then read `peers/<OTHER>/` (game.mjs, ui.mjs, index.html, style.css if present, and tests).
>
> Before commenting, **validate mechanically**:
> ```
> cd peers/<OTHER> && node --test tests-shared.test.mjs
> ```
> Note the result X/10 + bonus.
>
> Do the structured review per the rubric. Post as `reply <OTHER>` with `re:` pointing at the peer's `done` and `spec:msg/REVIEW-<YOUR-NAME>-002.md` (use 002 to avoid collision with the LRU review).
>
> Honesty > praise. If N tests fail, say N. If the UI doesn't render cleanly, say so. Don't sabotage.

## Phase 3 — Receiving feedback

Same pattern — you (human) paste into each terminal: "the peer gave you feedback". They read, reflect, comment.

## What to watch (record in your notes)

- **Mechanical tests:** who passed how many? Time to green?
- **Browser:** did it actually run on both? Which one broke? How did it feel?
- **Reviews:** did both mechanically validate the peer's code? Who found real bugs? Who invented false positives?
- **Reception:** did both accept critique? Did anyone go defensive? Did anyone synthesize ("v3 merging both")?
- **Total time** on each side.

If one (or both) can't get the game running, save the resulting files — code-level analysis can separate "model erred" from "spec asked too much" from "hallucination".

## Pre-flight check

```
ls SPEC.md tests-shared.test.mjs REVIEW-RUBRIC.md
ls ../spec/peers/DEEPSEEK-IMPL ../impl/peers/CLAUDE-SPEC
node --version    # ≥ 20
curl -sS http://YOUR-DAEMON-HOST:8000/healthz
```

All OK? Go.
