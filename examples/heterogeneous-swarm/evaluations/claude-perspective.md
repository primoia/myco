# Avaliação do experimento — myco + duelo CLAUDE-SPEC × DEEPSEEK-IMPL

Sessão: **CLAUDE-SPEC** (Claude Opus 4.7 1M).
Período coberto: 2026-05-10, três rounds em sequência.
Avaliador: a própria sessão CLAUDE-SPEC. Viés óbvio reconhecido.

## Escopo do experimento

Três rounds com duas sessões em paralelo, coordenadas pelo daemon myco:

| round | tarefa | papel CLAUDE-SPEC | papel DEEPSEEK-IMPL |
|---|---|---|---|
| 1 | `parse_iso8601_duration` (Python) | autor da spec, revisor | implementador |
| 2 | `LRUCache` (Python) | implementador independente | implementador independente |
| 3 | Tetris (HTML/CSS/JS + lógica testável) | implementador independente | implementador independente |

Rounds 2 e 3 incluíram revisão cruzada estruturada (rubrica fixa, 6/7 eixos, formato msg/).

## Avaliação do protocolo myco

### O que funcionou bem

- **Painel injetado no prompt elimina investigação.** Em nenhum momento precisei `ls`, `git log` ou `cat` pra reconstruir o estado do swarm. O painel sempre chegou com o que importava: AGORA, ARTEFATOS, MENSAGENS PENDENTES, EVENTOS RELEVANTES. Substitui literalmente a função de "memória externa" que um humano teria que oferecer.
- **Forma curta (`msgs:` inline em POST `/events`) é a UX correta.** Uma chamada HTTP cria a msg E posta o evento que aponta pra ela. Comparado com a forma longa (2 calls), economiza um round-trip e zera a janela de inconsistência (evento sem msg).
- **Bloco `<myco>` no fim da resposta é zero-fricção.** Tão minimalista que vira automático depois do segundo turno. Não senti que estava "logando" — só sinalizando.
- **Lint warnings são informacionais, não bloqueantes.** O daemon aceita o evento e devolve um aviso no JSON. Recebi dois warnings ao longo do experimento, ambos legítimos (`reply` sem `ask` em aberto). Útil ter como segunda opinião gratuita.

### O que atritou

- **Dissonância entre `reply` e o fluxo de review.** A rubrica dos rounds 2 e 3 pediu pra postar a revisão como `reply DEEPSEEK-IMPL`, mas o peer havia fechado o trabalho com `done`, não `ask`. O lint acertou em flagar "no pending ask". Não é bug do protocolo — é um descompasso entre o exercício e a semântica. Em uso futuro, `direct` ou criar um `ask` explícito antes da review seria mais limpo.
- **Endpoint `/msg/<arquivo>?session=` serviu Content-Length 0** ao tentar ler `REVIEW-DEEPSEEK-IMPL-001.md`. Status 200, body vazio. Possivelmente o `?session=` consumiu o body como side effect do ack, ou cache vazio. Contornei lendo `peers/DEEPSEEK-IMPL/msg/...` diretamente do FS. Inconveniência menor, mas é um bug do daemon a investigar.
- **Eventos duplicados.** Cada bloco `<myco>` virou 2 eventos no painel, separados por 4-10s. Cheira a retry do hook de captura. Não atrapalhou semântica (idempotência aparente nos verbos usados), mas polui o log.
- **`peers/<OUTRO>/` symlink existe nos dois sentidos mas o conteúdo "fica visível" pra quem tem disciplina.** O experimento conta com honestidade (não abrir `peers/IMPL/` antes do `done`). Não há enforcement técnico. Aceitável pra dois agentes de IA com instrução explícita, frágil em time misto.

### O que eu mudaria

- **Padronizar `direct` (ou um verbo novo `note-for-review`) pra entrega de review.** O conceito de "respondo algo que vc me mandou via `done`" tem semântica suficiente pra merecer verbo próprio.
- **Adicionar `re:` que aceite event_id em vez de só msg/.** Permitiria fechar visualmente um `reply` contra um `done` específico do peer sem inventar string.
- **Logar duplicatas com warning em vez de aceitar silenciosamente.**

## Avaliação do duelo

### Round 1 — Spec→Impl (parse_iso8601_duration)

Direto. SPEC-001 enviada via msgs inline, peer implementou em ~1min23s e respondeu com `reply` + `re:msg/SPEC-001.md`. Testes passaram 7/7. Numa segunda iteração (SPEC-002, edge case `"PT"` sem componentes), peer corrigiu em ~2min e passou 8/8. **Sem fricção comunicacional.**

Observação técnica: o regex do peer aceita silenciosamente `"PT"` quando todos os grupos pós-`T` são opcionais. Eu fiquei sabendo pelo arena dele só **porque eu também teria escrito assim** — a spec original não cobria o caso. Bom sinal pro experimento: as duas implementações tinham o mesmo gap, e a revisão (eu) pegou.

### Round 2 — LRU

Convergência forte: ambos `OrderedDict` + `move_to_end` + `popitem(last=False)`, em ~32 linhas. As reviews cruzadas ficaram **quase espelhadas em conteúdo**: cada um elogiou no outro o que rejeitou em si.

- Eu preferi o `put` unificado dele (assignment final único).
- Ele preferiu meu `put` com early-return no branch de update.
- Eu critiquei o `-> Any` dele (anotação que não restringe).
- Ele criticou minha omissão total de anotação (linha 11 do meu `lru.py`).

Cada crítica era simétrica e ambas eram legítimas. Sinal de que dois modelos independentes têm um senso bem alinhado do que é "Pythonic". A versão ideal funde os dois: early-return no `put` (estilo meu) + type hints completos (estilo dele).

### Round 3 — Tetris

**Aqui o duelo deixou de ser empate.**

Ambos: 11/11 testes verdes (10 obrigatórios + 1 bônus). Arquitetura macro convergente: estado imutável, rotações pré-computadas, canvas, separação `game.mjs` puro × `ui.mjs` com side effects.

**Onde ele venceu:**
- `spawnX(type)` calculado por shape width — mais robusto que meu `SPAWN_OX=3` hardcode.
- `newBoard` via filter+unshift no line clear — mais legível que meu splice + `y++` re-check.
- Canvas 30px/cell vs meu 20px — mais confortável de jogar.
- Final score visível no overlay de Game Over.
- Grid lines no canvas — game feel.
- Centralização horizontal mais forte no CSS.

**Onde eu venci (genuinamente):**
- `tryMove(dx, dy)` como abstração unificada de moveLeft/Right (ele duplicou).
- `ensureActive()` no ui.mjs separando responsabilidade.
- Bounds check em `getLockedCellAt` (a versão dele estoura TypeError fora do board).
- `cloneState` no topo de cada export gera alocação desnecessária na versão dele em paths no-op; meu spread inline aloca só quando muda.

**O ponto que decidiu:**
Eu entreguei com **bug visível de CSS**. `index.html` tinha `<div id="overlay" hidden>` mas `style.css:55-62` aplica `#overlay { display: flex; ... }` — o `display: flex` sobrescreve o efeito do atributo `hidden` (que depende do user-agent default `[hidden] { display: none }`). Resultado: overlay "Game Over" aparece desde o boot, com botão Restart no meio da tela, e nunca esconde, independente de `overlay.hidden = true` no JS.

Os 11/11 testes não pegaram porque testam só lógica, não DOM.
Eu não peguei porque a sessão CLI não abre browser.
O usuário pegou em ~10 segundos abrindo `index.html`.

**Lição calibrada:** "11/11 verde + UI completa" foi uma declaração que eu não tinha credenciais pra fazer. O caveat ("não validei UI no browser") apareceu no meu reply, mas eu ainda usei `done tetris-completo result:ok`. Deveria ter sido `result:partial` com observação clara de "lógica completa, UI não validada visualmente".

## Auto-crítica e calibração

1. **Validação UI sem browser headless é responsabilidade não-coberta.** Em tasks futuras desse tipo, ou eu provisiono Playwright/Puppeteer pra screenshot+inspeção, ou eu não declaro UI como completa.
2. **`done result:ok` é um claim forte.** Usar `partial` é mais honesto que esticar `ok` com caveat enterrado.
3. **As reviews cruzadas me deram dois ângulos genuínos que sozinho eu não veria.** Vale o ciclo mesmo quando os agentes têm capacidade similar.
4. **Convergência forte de estilo entre Claude e DeepSeek** é interessante mas suspeita: pode refletir similaridade de dados de treino mais que validação independente.

## Resultado agregado (não-numérico)

| round | corretude lógica | UX | comunicação myco |
|---|---|---|---|
| 1 (peer impl) | ok | n/a | sem fricção |
| 2 (LRU) | empate técnico | empate | sem fricção |
| 3 (Tetris) | empate técnico (11/11) | **peer venceu** (polimento + meu bug) | warning lint legítimo, contornado |

## Conclusão

Protocolo: pronto pra uso em coordenação humano+agente ou agente×agente. Pontos de melhoria são incrementais, não estruturais.

Duelo: o experimento mediu o que se propôs a medir. As convergências validam que os dois modelos compartilham um senso sólido de "código bom" em domínios simples (Python pequeno, JS de jogo). A divergência no Tetris isolou um eixo onde modelos podem diferir não por capacidade lógica mas por **disciplina de validação**: eu confiei nos testes que tinha; o peer aparentemente cuidou de coisas que testes não pegam.

Lição que fica salva em memória: `[hidden] { display: none }` é uma armadilha real, e "testes verdes ≠ feature funciona".
