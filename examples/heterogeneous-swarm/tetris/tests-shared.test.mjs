// Suíte oficial do duelo Tetris.
// Rodar com: node --test tests-shared.test.mjs
// Requer Node ≥20.
//
// 10 testes obrigatórios + 1 bônus (Tetris score).
// Ambas arenas devem ter este arquivo IDÊNTICO. Não modificar.

import { test } from 'node:test';
import assert from 'node:assert';
import {
  createGame,
  spawnPiece,
  moveLeft,
  moveRight,
  moveDown,
  rotateCW,
  tick,
  getActivePiece,
  getLockedCellAt,
  getScore,
  isGameOver,
  setLockedCells,
} from './game.mjs';

const ALL_PIECE_TYPES = ['I', 'O', 'T', 'S', 'Z', 'J', 'L'];

// ---------- 1. createGame ----------

test('createGame: 20x10 vazio, score 0, sem peça ativa, sem game over', () => {
  const s = createGame();
  for (let y = 0; y < 20; y++) {
    for (let x = 0; x < 10; x++) {
      assert.strictEqual(getLockedCellAt(s, x, y), 0,
        `cell (${x},${y}) deveria ser 0`);
    }
  }
  assert.strictEqual(getActivePiece(s), null);
  assert.strictEqual(getScore(s), 0);
  assert.strictEqual(isGameOver(s), false);
});

// ---------- 2. spawnPiece — todos os tipos ----------

test('spawnPiece: cada tipo coloca peça ativa com 4 células', () => {
  for (const type of ALL_PIECE_TYPES) {
    const s = spawnPiece(createGame(), type);
    const p = getActivePiece(s);
    assert.ok(p !== null, `peça ${type} deve estar ativa após spawn`);
    assert.strictEqual(p.type, type, `peça ativa deve ter type=${type}`);
    assert.strictEqual(p.cells.length, 4, `peça ${type} deve ter 4 células`);
    // cells dentro do board
    for (const c of p.cells) {
      assert.ok(c.x >= 0 && c.x < 10, `cell.x=${c.x} fora do board`);
      assert.ok(c.y >= 0 && c.y < 20, `cell.y=${c.y} fora do board`);
    }
  }
});

// ---------- 3. moveLeft / moveRight movem ativa ----------

test('moveLeft e moveRight movem a peça ativa em 1 coluna', () => {
  let s = spawnPiece(createGame(), 'O');
  const before = getActivePiece(s);

  s = moveLeft(s);
  const left = getActivePiece(s);
  for (let i = 0; i < before.cells.length; i++) {
    assert.strictEqual(left.cells[i].x, before.cells[i].x - 1);
    assert.strictEqual(left.cells[i].y, before.cells[i].y);
  }

  // moveRight cancela o moveLeft
  s = moveRight(s);
  const right = getActivePiece(s);
  for (let i = 0; i < before.cells.length; i++) {
    assert.strictEqual(right.cells[i].x, before.cells[i].x);
    assert.strictEqual(right.cells[i].y, before.cells[i].y);
  }
});

// ---------- 4. moveLeft no edge esquerdo é no-op ----------

test('moveLeft no edge esquerdo não muda estado', () => {
  let s = spawnPiece(createGame(), 'O');
  for (let i = 0; i < 20; i++) s = moveLeft(s);
  const stuck = getActivePiece(s);
  s = moveLeft(s);
  const tryAgain = getActivePiece(s);
  assert.deepStrictEqual(tryAgain.cells, stuck.cells);
});

// ---------- 5. rotateCW muda orientação ----------

test('rotateCW muda orientação da peça I (não-O)', () => {
  let s = spawnPiece(createGame(), 'I');
  const before = getActivePiece(s);
  const beforeXs = new Set(before.cells.map(c => c.x));

  s = rotateCW(s);
  const after = getActivePiece(s);
  const afterXs = new Set(after.cells.map(c => c.x));

  // I horizontal: 4 xs distintos. I vertical: 1 x.
  // Esperamos que o tamanho do conjunto mude.
  assert.notStrictEqual(beforeXs.size, afterXs.size,
    'rotação de I deve alterar distribuição em x (h↔v)');
});

// ---------- 6. tick gravita a peça uma linha pra baixo ----------

test('tick desce a peça ativa uma linha (gravidade)', () => {
  let s = spawnPiece(createGame(), 'T');
  const before = getActivePiece(s);
  s = tick(s);
  const after = getActivePiece(s);
  if (after === null) {
    // Improvável (peça nasce no topo), mas se travou imediatamente, falha
    assert.fail('tick não deveria travar peça que acabou de spawnar');
  }
  for (let i = 0; i < before.cells.length; i++) {
    assert.strictEqual(after.cells[i].y, before.cells[i].y + 1);
    assert.strictEqual(after.cells[i].x, before.cells[i].x);
  }
});

// ---------- 7. moveDown trava peça quando não pode descer ----------

test('moveDown trava peça quando atinge o chão', () => {
  let s = spawnPiece(createGame(), 'O');
  // soft-drop até travar (board é 20 linhas; spawn no topo; até 25 ticks suficiente)
  for (let i = 0; i < 25; i++) s = moveDown(s);

  // peça ativa deve ter virado null após o lock
  assert.strictEqual(getActivePiece(s), null,
    'peça ativa deve ser null após lock automático');

  // bottom row tem células locked (peça O ocupa 2 colunas)
  let lockedAtBottom = 0;
  for (let x = 0; x < 10; x++) {
    if (getLockedCellAt(s, x, 19) !== 0) lockedAtBottom++;
  }
  assert.ok(lockedAtBottom >= 2, `bottom row deveria ter ≥2 cells locked, tem ${lockedAtBottom}`);
});

// ---------- 8. setLockedCells é "no-op semântico" — não dispara clear ----------

test('setLockedCells preenche cells sem disparar line-clear nem score', () => {
  let s = createGame();
  const cells = [];
  for (let x = 0; x < 10; x++) cells.push({ x, y: 19, type: 1 });
  s = setLockedCells(s, cells);

  // todas as 10 cells da linha 19 devem estar locked
  for (let x = 0; x < 10; x++) {
    assert.notStrictEqual(getLockedCellAt(s, x, 19), 0,
      `cell (${x},19) deveria estar locked após setLockedCells`);
  }
  // mas score continua 0 (utility não dispara scoring)
  assert.strictEqual(getScore(s), 0,
    'setLockedCells é utility de teste — não deve mexer em score');
});

// ---------- 9. clear de 1 linha + score +100 ----------

test('lock que completa 1 linha: linha some, acima desce, score +100', () => {
  let s = createGame();
  // pré-encher linha 19 deixando coluna 4 vazia
  const cells = [];
  for (let x = 0; x < 10; x++) {
    if (x !== 4) cells.push({ x, y: 19, type: 1 });
  }
  s = setLockedCells(s, cells);
  assert.strictEqual(getScore(s), 0);

  // setup: forçar uma única célula a cair em (4, 19)
  // estratégia simples: setLockedCells em (4, 18) e abaixo... não, queremos lock real.
  // uso peça I rotacionada vertical na coluna 4: ocupa (4,16..19).
  // Quando travar, linha 19 fica completa → clear → linhas acima descem 1.

  s = spawnPiece(s, 'I');
  s = rotateCW(s); // I vertical
  // mover ativa pra coluna 4
  let p = getActivePiece(s);
  if (p === null) assert.fail('peça I deveria ativa após spawn+rotate');
  // ler x da coluna ocupada (vertical = 1 coluna)
  const targetX = 4;
  let currentX = p.cells[0].x;
  let safety = 30;
  while (currentX !== targetX && safety-- > 0) {
    s = currentX > targetX ? moveLeft(s) : moveRight(s);
    const np = getActivePiece(s);
    if (np === null) break;
    if (np.cells[0].x === currentX) break; // não conseguiu mover
    currentX = np.cells[0].x;
  }
  // soft-drop até travar
  let dropSafety = 30;
  while (getActivePiece(s) !== null && dropSafety-- > 0) {
    s = moveDown(s);
  }

  // linha 19 deve ter sido limpa (1 cell sobrou onde o I-piece deixou cells acima)
  // após clear de linha 19, as cells (4, 16..18) descem para (4, 17..19).
  // sobre (4, 19) deve haver cell locked (vinda do I).
  const cellAt4_19 = getLockedCellAt(s, 4, 19);
  assert.notStrictEqual(cellAt4_19, 0, '(4,19) deveria ter cell locked após clear');

  // cells originais da linha 19 (que eram type 1) sumiram
  // vamos checar que pelo menos uma cell (que NÃO está em x=4) na linha 19 sumiu
  // se (3,19) por exemplo estava em type 1 e linha 19 foi limpa, então (3,19) é 0 agora
  // (a menos que cells acima desceram pra ele — mas só (4, ...) tinham cells acima)
  assert.strictEqual(getLockedCellAt(s, 0, 19), 0, '(0,19) deveria ter sumido (linha foi limpa)');
  assert.strictEqual(getLockedCellAt(s, 3, 19), 0, '(3,19) deveria ter sumido');

  // score: +100 por uma linha
  assert.strictEqual(getScore(s), 100,
    `score deveria ser 100 após 1 linha, é ${getScore(s)}`);
});

// ---------- 10. game over: spawn sobre cells ocupadas ----------

test('game over: spawn em cells ocupadas marca isGameOver=true', () => {
  let s = createGame();
  // bloquear o topo do board (onde peças nascem)
  const blockingCells = [];
  for (let y = 0; y < 4; y++) {
    for (let x = 3; x < 7; x++) {
      blockingCells.push({ x, y, type: 1 });
    }
  }
  s = setLockedCells(s, blockingCells);

  // spawn de qualquer peça deve marcar gameOver
  s = spawnPiece(s, 'O');
  assert.strictEqual(isGameOver(s), true,
    'spawn em região ocupada deveria marcar gameOver=true');
});

// ---------- BÔNUS — Tetris (4 linhas) score +800 ----------

test('[BÔNUS] Tetris: 4 linhas limpas em um único lock = +800', () => {
  let s = createGame();
  // pré-encher linhas 16, 17, 18, 19 deixando coluna 4 vazia em todas
  const cells = [];
  for (let y = 16; y <= 19; y++) {
    for (let x = 0; x < 10; x++) {
      if (x !== 4) cells.push({ x, y, type: 1 });
    }
  }
  s = setLockedCells(s, cells);

  // lança I-piece vertical pra coluna 4 → preenche (4, 16..19) → 4 linhas completas
  s = spawnPiece(s, 'I');
  s = rotateCW(s);

  // mover I pra coluna 4
  let safety = 30;
  let p = getActivePiece(s);
  while (p && p.cells[0].x !== 4 && safety-- > 0) {
    const nextS = p.cells[0].x > 4 ? moveLeft(s) : moveRight(s);
    const np = getActivePiece(nextS);
    if (!np || np.cells[0].x === p.cells[0].x) break;
    s = nextS;
    p = np;
  }

  // soft-drop até travar
  let dropSafety = 30;
  while (getActivePiece(s) !== null && dropSafety-- > 0) {
    s = moveDown(s);
  }

  // 4 linhas limpas → score 800
  assert.strictEqual(getScore(s), 800,
    `Tetris (4 linhas) deveria scorar 800, scorou ${getScore(s)}`);
});
