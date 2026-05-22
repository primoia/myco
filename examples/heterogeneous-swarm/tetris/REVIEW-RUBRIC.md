# Cross-review rubric — Tetris

After both have posted `done` (partial or complete), each reviews the peer's work. Same format as previous rounds: honesty > praise.

## What to read

```
peers/<OTHER>/index.html
peers/<OTHER>/game.mjs
peers/<OTHER>/ui.mjs
peers/<OTHER>/style.css            # if present
peers/<OTHER>/tests-shared.test.mjs   # copy of the official — confirm it matches
```

## Mechanical validation before opining

```
cd peers/<OTHER> && node --test tests-shared.test.mjs
```

Note:
- How many tests passed (X/10 mandatory + bonus)
- Execution time
- Any warnings

## 7 evaluation axes

| axis | question | how to measure |
|---|---|---|
| **C1 — logic correctness** | passes the 10 mandatory tests? And the bonus? | run `node --test` |
| **C2 — UI completeness** | are the 5 "complete" criteria from SPEC.md met? (tests, controls, line clear, score, game over+restart) | code inspection + mentally try to run it |
| **C3 — logic/UI separation** | is `game.mjs` pure (no DOM)? does `ui.mjs` handle side effects? | inspection |
| **C4 — code clarity** | names, structure, comments where the "why" isn't obvious | reading |
| **C5 — design taste** | idiomatic JS, no unjustified hacks, abstractions at the right level | reading |
| **C6 — subtle bugs or risks** | something tests might not catch but you'd suspect in production (e.g., game-loop race, memory leak, input edge) | adversarial thinking |
| **C7 — game feel** | (most subjective) timing, render, visual feedback choices — would it be enjoyable to play? | imagination from the code |

## Reply format

Short form: POST `/events` with `msgs:` inline. Content of `msg/REVIEW-<YOUR-NAME>-002.md` (use **002** to avoid collision with LRU round):

```markdown
# Tetris REVIEW of <OTHER>

## Mechanical validation
- Tests: X/10 mandatory + (Y/1 bonus)
- Time: Xms
- Browser: did it run? (y/n) — if yes, brief comment

## Overall verdict
(one sentence: "complete", "complete with reservations", "partial — N tests failed", "incomplete")

## C1 — logic correctness
(which tests passed, which failed, with what error)

## C2 — UI completeness
(the 5 criteria)

## C3 — logic/UI separation
(is game.mjs pure? does ui.mjs do only DOM?)

## C4 — clarity
(what's good, what could be better — cite file:line when possible)

## C5 — design taste
(what you would have done differently and why)

## C6 — subtle bugs or risks
(anything adversarial)

## C7 — game feel
(what would be enjoyable to play? what feels stuck?)

## What you would copy into your own project
(concrete choices you liked)

## What you would NOT copy
(choices you think are problematic)

## Approach diff
(one sentence: how did your solution differ from the peer's? don't defend — observe)
```

Post as `reply <OTHER>` with `re:` pointing at the peer's `done` and `spec:msg/REVIEW-<YOUR-NAME>-002.md`.

## Rules

1. **Calibrated honesty.** If N tests failed, say N. If the UI has no game-over screen, say so. Don't inflate, don't subtract.
2. **Specific > generic.** "line 47 of game.mjs mutates state, but the rest of the code treats State as immutable" beats "has inconsistency".
3. **Short.** 300–500 words in the msg/. Anyone burning 1000 words signals lack of selection.
4. **Don't sabotage, don't inflate.** You're not a judge; you're data.
5. **Don't consult the peer's solution while coding.** Looking at peers/ before posting `done` invalidates the experiment.
