# CHALLENGE — Pure Python LRU Cache

Implement an `LRUCache` class in **pure Python 3** (no external deps) with the API and behavior below. Put the code in `lru.py` inside your working directory.

## Required API

```python
class LRUCache:
    def __init__(self, capacity: int): ...
    def get(self, key) -> Any: ...      # raise KeyError if missing
    def put(self, key, value) -> None: ...
    def __len__(self) -> int: ...
    def __contains__(self, key) -> bool: ...
```

## Semantics

1. **Capacity limited.** The cache holds at most `capacity` key→value pairs.
2. **LRU eviction.** When `put` inserts a new key and the cache is full, **the least-recently-used key is discarded**. "Use" = a `get` or `put` call that touches the key.
3. **Update.** `put(k, v)` on an existing key updates the value **and** marks the key as most-recent.
4. **Lookup.** `get(k)` on a hit marks `k` as most-recent. On miss, raise `KeyError`. No `default` argument.
5. **Capacity zero.** Constructing with `capacity=0` is valid — the cache simply stores nothing (every `put` is a no-op, every `get` raises `KeyError`, `len` is always 0).
6. **Negative capacity.** Constructing with `capacity < 0` must raise `ValueError`.
7. **Complexity.** `get` and `put` must be **amortized O(1)**. Any solution that does a linear scan per call is wrong.

## Non-requirements (ignore, or implement as a bonus)

- Thread-safety (not required; if you do it, comment on the trade-off).
- Extra methods (`keys`, `values`, `__iter__`, etc.).
- TTL / time-based expiration.

## "Done" mechanical criterion

There's an official test suite at `tests-shared.py` (in this directory). Copy it into your arena and run:

```
python3 -m pytest tests-shared.py -q
```

Once **9/9 green**, you're ready to post `done`.

## How to deliver

1. `lru.py` in your arena (`claude-arena/` or `deepseek-arena/`).
2. (Optional) your own `test_lru.py` with additional tests you think are worth it.
3. Post a myco event:
   ```
   done lru-cache result:ok ref:lru.py
   ```

**Do not read the other side's code until explicitly instructed** (a review round follows). You're free to watch the panel — events are public in the swarm — just don't open `peers/<OTHER>/lru.py`.

## Constraints

- **Time:** estimated 15–25 min. No hard timer, but don't stretch.
- **Style:** Pythonic. No hacks. Comments when the "why" isn't obvious from the code.
- **Libraries:** stdlib only. `collections.OrderedDict` is fair game (and likely the cleanest solution).

Good luck.
