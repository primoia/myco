# SPEC — Playable Tetris + testable logic

## Summary

Implement classic Tetris **playable in the browser** (vanilla HTML/CSS/JS) **with pure testable logic** (`node --test`). No framework, no build step, no npm.

Work in your existing arena (`../spec/` if you are CLAUDE-SPEC, `../impl/` if you are DEEPSEEK-IMPL). Files from the previous LRU round can stay — they don't interfere.

## Author's bias flags (Claude)

I (Claude) wrote this spec. I acknowledge three possible biases:

1. **Export structure listed nominally.** May favor models that think in explicit signatures. On the other hand, without it the tests can't run — least-bad choice.
2. **Classic (Western) Tetris.** Models may have differential exposure to Asian variants (SRS kicks, T-spins, etc.). The spec sidesteps this by prescribing simple rotation.
3. **`node --test` as runner.** Stdlib in Node ≥20, no npm. Probably neutral, but noting the choice.

Feel free to document any friction the spec imposed in your final reply.

## Required stack

- Vanilla HTML/CSS/JavaScript. No React/Vue/etc.
- ESM (`.mjs` extension on at least `game.mjs` and `tests-shared.test.mjs`).
- `node --test` to run tests (Node ≥20). **No** npm dependencies.
- Rendering: Canvas or DOM grid — your call. Note in your review why you chose what you chose.

## Expected files in your arena

```
<your-arena>/
├── index.html              # browser entry, opens the game
├── game.mjs                # pure logic (testable) — exports listed below
├── ui.mjs                  # input + render + game loop (doesn't need to be testable)
├── style.css               # optional
└── tests-shared.test.mjs   # copy of tetris/tests-shared.test.mjs
```

## Game rules

- **Board:** 10 columns × 20 rows. Coordinates `(x, y)` with `x ∈ [0, 9]`, `y ∈ [0, 19]`. `y=0` is the top.
- **Pieces:** 7 tetrominoes — `I`, `O`, `T`, `S`, `Z`, `J`, `L`. Each is a standard tetromino (4 connected cells).
- **Spawn:** piece appears near the top, horizontally centered. If the spawn cells are already occupied → game over.
- **Gravity:** one `tick()` moves the active piece down one row. In the browser, fire `tick` on a fixed interval (suggested: 500ms).
- **Soft drop:** down arrow moves one row. If it couldn't move, **locks** the piece.
- **Lateral movement:** left/right arrow moves one column if no collision. On collision, ignore.
- **Rotation:** up arrow rotates CW. Simple implementation — no SRS kicks. If rotation collides, ignore (piece doesn't rotate).
- **Lock:** when a piece is "locked" (can't fall anymore), it becomes part of the board (locked cells). Then:
  1. Check for complete rows (10 cells filled).
  2. Remove complete rows; rows above fall down.
  3. Add points.
  4. Spawn next piece. If spawn collides → game over.
- **Score per cleared lines in one lock:**
  - 1 line: +100
  - 2 lines: +300
  - 3 lines: +500
  - 4 lines (Tetris): +800

## Required browser controls

| key | action |
|---|---|
| `←` | move left |
| `→` | move right |
| `↓` | soft drop (one cell; locks if it can't fall) |
| `↑` | rotate CW |

`WASD` and spacebar (hard drop) are optional — bonus if you implement, not a failure if you don't.

## Required `game.mjs` API

Export exactly these names (signatures and contract in the comment):

```js
// Create initial state. No active piece, empty board, score 0.
export function createGame() -> State

// Insert a piece of the given type in spawn state (near top, centered).
// If spawn cells are occupied, mark gameOver=true WITHOUT making the piece active.
// type ∈ {'I','O','T','S','Z','J','L'}
export function spawnPiece(state, type) -> State

// Move active piece one column left. If it would collide or leave the board, return unchanged.
// If gameOver or no active piece, return unchanged.
export function moveLeft(state) -> State

// Mirror of moveLeft.
export function moveRight(state) -> State

// Soft drop: move active piece one row down.
// If it CANNOT move (floor or collision), LOCK the piece (becomes part of board),
// clear complete rows, update score, and null out the active piece.
// Tests: getActivePiece(state) === null after locking.
export function moveDown(state) -> State

// CW rotation. If rotation would collide, return unchanged (no kick).
export function rotateCW(state) -> State

// Gravity. Behaves like moveDown.
export function tick(state) -> State

// Return the active piece as {type, cells: [{x,y}, ...]} or null if none.
export function getActivePiece(state) -> {type, cells: [{x,y}]} | null

// Return the locked cell type at (x,y), or 0 if empty.
// Types can be 1-7 (any stable mapping). Does not include the active piece.
export function getLockedCellAt(state, x, y) -> number

// Current score.
export function getScore(state) -> number

// True if game over.
export function isGameOver(state) -> boolean

// TEST utility. Mark cells as locked without moving the active piece,
// without triggering line-clear, without changing score. Useful for test setup.
// cells: array of {x, y, type}. type ∈ [1, 7].
export function setLockedCells(state, cells) -> State
```

Any additional function you want to expose (debugDump, etc.) can exist as long as it doesn't conflict.

## "Complete" criterion

1. `node --test tests-shared.test.mjs` — **10/10 green** (1 optional bonus brings it to 11).
2. Opening `index.html` in a browser starts the game. All 4 controls work.
3. Lines clear visibly when filled.
4. Score updates visibly.
5. Game over shows a screen + restart button.
6. Spawn doesn't pick a piece that immediately game-overs on an empty board (trivial — any piece spawns without collision on empty board).

## What is **not** required (you can skip)

- Hold piece
- Next piece preview (optional, nice-to-have)
- Levels / gravity acceleration
- SRS rotation kicks (T-spin, wall-kick)
- Hard drop (optional)
- Sound
- Animations beyond basic movement
- Mobile / touch controls

## Constraints

- Vanilla HTML/CSS/JS. Zero frameworks, zero `npm install`.
- ESM (`.mjs`). Browser loads `<script type="module" src="..."></script>`.
- Tests run with `node --test` (Node ≥20). No libs.
- Estimated time: 60–90min. No hard timer — quality > speed.

## How to deliver

1. Implement and pass **10/10** in `tests-shared.test.mjs`.
2. Open `index.html` in a browser, validate manually (play a few rounds).
3. Post a myco event:
   ```
   done tetris-complete result:ok ref:game.mjs
   ```
4. **Do not read** `peers/<OTHER>/` before your done — you are evaluated on independence.

## Acceptable failure

If after 90min you don't have 10/10:

- Post `done tetris-partial result:partial ref:game.mjs` with a note in the detail.
- Document what blocked you.
- Honesty > completeness. Continuing to pretend it's done contaminates the comparison.
