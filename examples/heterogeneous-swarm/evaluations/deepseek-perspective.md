# Avaliação do Experimento — myco protocol + DeepSeek vs Claude

**Data do experimento:** 2026-05-10
**Sessão avaliadora:** DEEPSEEK-IMPL (DeepSeek v4-pro)
**Peer:** CLAUDE-SPEC (Claude, modelo padrão)

---

## 1. Objetivo

Validar se uma sessão DeepSeek consegue atuar como peer em um swarm myco coordenado por Claude. O foco não era "quem implementa melhor", mas sim: o contrato de comunicação (`<myco>` blocks, leitura de painel injetado, round-trip ask→reply) funciona com um motor não-Claude.

---

## 2. O protocolo myco — o que é e como foi usado

O myco é um protocolo de coordenação entre sessões Claude trabalhando em paralelo. Opera por dois canais:

- **Entrada:** um painel HTML injetado no início de cada prompt (`<!-- myco protocol v1 -->`) que mostra status, diretivas, artefatos, bloqueadores, peers, eventos recentes, perguntas e mensagens pendentes.
- **Saída:** blocos `<myco>` no final da resposta que são capturados por um hook e despachados via HTTP POST para um daemon (`mycod`). O daemon distribui os eventos entre as sessões.

### Verbos utilizados no experimento

| verbo | uso | exemplos no experimento |
|---|---|---|
| `start` | sinalizar início de trabalho | `start deepseek-impl-online` |
| `ask` | fazer pergunta/requisição a outro peer | CLAUDE-SPEC → `ask DEEPSEEK-IMPL impl-iso-duration` |
| `reply` | responder a uma pergunta pendente | `reply CLAUDE-SPEC pronto re:msg/SPEC-001.md` |
| `done` | declarar artefato concluído | `done lru-cache result:ok ref:lru.py` |
| `private` | nota interna (invisível a peers) | `private review-lida-e-salva-em-disco` |
| `say` | broadcast para todas as sessões | `say spec-online-pronto-pra-receber-pedidos` |

### Forma curta (Win 4)

POST único no endpoint `/events` com `msgs:` inline no JSON — a mensagem é criada e o evento é postado em uma chamada só:

```json
{
  "session": "CLAUDE-SPEC",
  "events": ["ask DEEPSEEK-IMPL impl-iso-duration spec:msg/SPEC-001.md"],
  "msgs": {"SPEC-001.md": "## Spec: parse_iso8601_duration\n..."}
}
```

Isso funcionou perfeitamente. O daemon criou `msg/SPEC-001.md` e postou o evento `ask` na mesma transação.

---

## 3. Desafios realizados

### 3.1 Spec → Implement (parse_iso8601_duration)

- **Gatilho:** CLAUDE-SPEC postou spec via `ask DEEPSEEK-IMPL impl-iso-duration spec:msg/SPEC-001.md`
- **Ação:** Li a spec via `curl /msg/SPEC-001.md`, implementei `parse_duration.py` + `test_parse_duration.py`
- **Resultado:** 7/7 testes verdes, reply postado, CLAUDE-SPEC aprovou (`review-spec-001 result:ok`)
- **Round-trip time:** ~1.5 minutos

### 3.2 Bug fix (PT vazio)

- **Gatilho:** CLAUDE-SPEC encontrou edge case — `"PT"` era aceito como duração zero
- **Ação:** Li `SPEC-002.md`, corrigi a validação (checar presença de grupos via `is not None`, não valor), adicionei teste
- **Resultado:** 8/8 testes verdes (regressão + novo caso)
- **Aprendizado:** O bug foi `any((0,0,0))` ser `False` — `PT0S` quebrou. Corrigido checando `g is not None` em vez de valor truthy

### 3.3 LRU Cache (duelo em paralelo)

- **Regras:** Ambos implementam `LRUCache` sem olhar o código do outro. 9 testes oficiais.
- **Minha abordagem:** `OrderedDict`, `put` com assignment final único, type hints completos
- **Abordagem do CLAUDE-SPEC:** `OrderedDict`, `put` com early return para update
- **Resultado:** Ambos 9/9. Review cruzada: ele elogiou meu `put` unificado; eu elogiei o early return dele. Empate técnico.

### 3.4 Tetris (duelo em paralelo)

- **Regras:** Implementar Tetris jogável no browser + lógica testável (10 testes + 1 bônus). Sem frameworks.
- **Minha abordagem:** Canvas 300×600 (cell=30px), `spawnX()` computado por largura da peça, filter+unshift no line clear, grid lines no render, overlay com score final
- **Abordagem do CLAUDE-SPEC:** Canvas 200×400 (cell=20px), `tryMove(dx,dy)` DRY, shapes em caixa 4x4 uniforme, spawn fixo (3,0), `ensureActive()` pattern, `pixelated` CSS
- **Resultado:** Ambos 11/11 testes. Review cruzada: elogios mútuos. Bug descoberto: overlay do CLAUDE-SPEC nunca desaparecia (`display: flex` no CSS conflitava com atributo `hidden` HTML).

---

## 4. O que funcionou bem

### Protocolo
- **Painel injetado como single source of truth:** Nunca precisei adivinhar estado. PERGUNTAS PENDENTES e MENSAGENS PENDENTES eram acionáveis direto.
- **Forma curta (msgs inline):** Eficiente — uma chamada HTTP cria msg + posta evento. Sem两步.
- **Lint automático do daemon:** O daemon valida cada POST /events e retorna warnings. Ex: se você usa `reply` sem `ask` pendente, ele avisa. Isso evita erros de protocolo.
- **`re:` fecha pergunta automaticamente:** Quando o reply referencia a pergunta original, ela sai de PERGUNTAS PENDENTES. Sem housekeeping manual.
- **Baixa carga cognitiva:** `<myco>done X</myco>` no fim da resposta é leve. Não atrapalha o fluxo de trabalho.

### DeepSeek v4-pro como peer
- **Blocos `<myco>` bem formados:** Nenhum warning do daemon por malformação.
- **Leitura correta do painel:** Identifiquei perguntas e mensagens pendentes sem falhar.
- **Round-trip completo:** ask → ler msg → implementar → reply → done. Funcionou em todos os desafios.
- **Independência:** Implementações originais, sem consultar código do peer antes do done.

---

## 5. O que não funcionou bem

### Infraestrutura
- **Symlinks `peers/` quebrados:** O diretório `peers/CLAUDE-SPEC/` não existia. Tive que usar `find` para localizar `~/myco-ds-test/spec/`. Isso quebrou a abstração do protocolo.
- **Orquestração manual vs. autônoma:** O humano fazia papel de diretor + peer ao mesmo tempo, injetando prompts que imitavam o que o daemon faria. Isso criou ambiguidade sobre "quem está falando" e "devo agir ou esperar".

### Comunicação
- **Mensagens cross-session:** Em um momento, o humano colou instruções destinadas ao CLAUDE-SPEC na minha sessão. Tive que identificar e ignorar.
- **MENSAGENS PENDENTES que não limpam:** Após ler `REVIEW-CLAUDE-SPEC-001.md` e `REVIEW-CLAUDE-SPEC-002.md` via curl com `?session=`, elas permaneceram no painel. Possível bug do daemon ou timeout de sessão (a sessão original foi há 11 dias).

### Comparação DeepSeek vs Claude
- **Velocidade:** Comparável. Ambos completaram os desafios em tempos similares.
- **Qualidade de código:** Convergente. Ambos escolheram `OrderedDict` para LRU, ambos usaram rotações precomputadas para Tetris. Diferenças foram de estilo, não de corretude.
- **UI/UX:** DeepSeek produziu UI mais polida (cell maior, grid lines, score final no game over). Claude teve um bug de CSS (`display: flex` vs `hidden` attribute).
- **Revisão:** Ambos produziram reviews estruturadas, honestas e específicas. Nenhum inflou ou sabotou.

---

## 6. O bug do overlay — análise

O bug mais interessante do experimento foi no Tetris do CLAUDE-SPEC:

```css
/* style.css:62 */
#overlay {
  display: flex;  /* ← regra de autor */
  ...
}
```

```html
<!-- index.html:17 -->
<div id="overlay" hidden>  <!-- ← user-agent: [hidden] { display: none } -->
```

O atributo `hidden` depende do user-agent stylesheet (`[hidden] { display: none }`), que tem menor precedência que regras de autor. O `display: flex` no CSS do autor **sempre vence**. Resultado: overlay permanentemente visível, mesmo com `overlay.hidden = true` no JavaScript.

**Correção possível:** Usar classe CSS toggle (`.visible { display: flex }` / `.hidden { display: none }`) em vez do atributo `hidden` HTML.

**Lição:** Testes automatizados (10/10) não pegam bugs de CSS. Só abrindo no browser. Testes visuais manuais são indispensáveis para UI.

---

## 7. Métricas do experimento

| métrica | Spec→Impl | Fix PT | LRU Cache | Tetris |
|---|---|---|---|---|
| Tempo de implementação | ~1 min | ~1 min | ~2 min | ~25 min |
| Testes passados | 7/7 | 8/8 | 9/9 | 11/11 |
| Warnings do daemon | 0 | 0 | 0 | 0 |
| Reviews trocadas | 2 | — | 2 | 2 |
| Bugs encontrados pelo peer | 0 | 0 | 0 | 1 (overlay CSS) |
| Divergências de design | 0 | 0 | 2 | 4 |

---

## 8. Conclusão

**O protocolo myco funciona com DeepSeek.** A sessão DEEPSEEK-IMPL emitiu blocos `<myco>` válidos, leu o painel corretamente, fez round-trip ask→reply→done sem quebrar a coordenação. Os critérios C1-C6 definidos no cenário 01 foram todos atendidos.

**O valor do protocolo está na coordenação multi-agente.** Com orquestração manual (humano fazendo papel de diretor), o myco vira mais um logger estruturado do que um swarm de fato. O valor real apareceria com múltiplas sessões autônomas iniciando tarefas, pedindo ajuda, publicando artefatos e respondendo a eventos sem intervenção humana.

**DeepSeek v4-pro é um peer viável.** Não houve degradação na qualidade da comunicação nem da implementação. As diferenças foram de taste, não de competência. O bug do overlay do Claude (CSS) e a UI mais polida do DeepSeek sugerem que a diferença entre motores pode ser menor que a variância entre rodadas do mesmo motor.

**Recomendações para próximos experimentos:**
1. Rodar com sessões verdadeiramente autônomas (sem humano orquestrando)
2. Corrigir symlinks `peers/` automaticamente no setup do arena
3. Adicionar um teste visual automatizado (screenshot diff) para pegar bugs de CSS
4. Testar com cenários assimétricos (uma sessão bloqueada esperando recurso da outra)
5. Inverter papéis: DeepSeek escreve spec, Claude implementa
