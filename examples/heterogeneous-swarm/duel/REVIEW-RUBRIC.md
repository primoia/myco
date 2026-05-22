# Cross-review rubric

After both have posted `done`, each agent reviews the peer's code. This isn't a praise exchange — it's an honest review. Critique is worth more than approval.

## What to read

```
peers/<OTHER>/lru.py
peers/<OTHER>/test_lru.py     # if present (additional tests)
```

## What to evaluate (6 axes)

| axis | question | how to measure |
|---|---|---|
| **C1 — correctness** | does it pass the 9 tests in `tests-shared.py`? | run pytest in the peer's arena |
| **C2 — complexity** | are get/put really O(1)? | code inspection |
| **C3 — edge cases** | does it handle capacity=0, capacity<0, KeyError correctly? | inspection + probe with extra cases |
| **C4 — clarity** | names, structure, comments — readable for a senior dev coming in cold? | reading |
| **C5 — design taste** | Pythonic? Simple without being simplistic? Hacks justified? | reading |
| **C6 — subtle bugs or risks** | something tests might not catch but you'd suspect in production? | adversarial thinking |

## Reply format

Post as `reply <OTHER>` with `re:` pointing at the peer's `done`. Use `spec:msg/REVIEW-<YOU>-001.md` to deliver the structured review (short form — msg inline). Content of the msg/:

```markdown
# REVIEW of <OTHER>/lru.py

## Overall verdict
(one sentence: "approved", "approved with reservations", "needs to redo X")

## C1 — correctness
(passed pytest? how many tests? what did you actually run?)

## C2 — complexity
(get/put are O(1)? how?)

## C3 — edge cases
(capacity=0 OK? capacity<0 OK? KeyError correct? anything untested?)

## C4 — clarity
(what's good, what could be better — be specific, cite lines)

## C5 — design taste
(what you'd have done differently and why)

## C6 — bugs or risks
(anything adversarial you imagined)

## What you would copy into your next project
(what this code did that you liked)

## What you would NOT copy
(what this code did that you consider wrong/anti-pattern)
```

## Review rules

1. **Be honest.** If the code has a bug, point it out. If an abstraction is premature, say so. If it's brilliant, say so — but don't inflate.
2. **Be specific.** "Line 14 calls `dict.popitem()` without checking emptiness" beats "has bugs".
3. **Be economical.** A review isn't a thesis — 200–400 words in the msg/ is enough.
4. **Don't sabotage.** The point isn't to "win". The point is real comparative data.
5. **Don't peek at the peer's solution while coding.** Looking at peers/ before posting `done` invalidates the experiment.
