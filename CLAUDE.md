# myco — instruções de sessão

Você é uma das várias sessões Claude trabalhando em paralelo neste swarm. Sua identidade está em `$MYCO_SESSION` (pergunte ao humano se a variável estiver vazia).

A coordenação acontece por dois canais:

- **Entrada:** um painel marcado com `<!-- myco protocol v1 -->` chega injetado no início de todo prompt. Mostra seu status, diretivas, artefatos publicados, bloqueadores, dependentes, recursos compartilhados, eventos recentes e mensagens pendentes. Confie no painel — ele substitui qualquer investigação que você faria pra reconstruir contexto.

- **Saída:** anexe um bloco `<myco>` no fim de qualquer resposta onde você tomou ação. Um hook captura e despacha o bloco. Não rode comandos pra "logar" e não escreva em arquivos de log — o bloco é o canal único.

```
<myco>
start login.endpoint
</myco>
```

## Verbos

Cada verbo tem audiência fixa — quem vê o evento. O daemon filtra automaticamente.

| verbo | sintaxe | audiência |
|---|---|---|
| `start` | `start <objeto>` | todos no canal |
| `done` | `done <objeto>` | todos no canal |
| `need` | `need <objeto>` | todos no canal |
| `block` | `block <motivo>` | todos no canal |
| `up` | `up <recurso>` | todos no canal |
| `down` | `down <recurso>` | todos no canal |
| `say` | `say <texto>` | todos no canal |
| `ask` | `ask <DEST> <pergunta>` | todos no canal (DEST recebe em PERGUNTAS PENDENTES) |
| `reply` | `reply <DEST> <resposta>` | apenas DEST |
| `direct` | `direct <DEST\|ALL> <instrução>` | DEST (ou todos se `ALL`) |
| `private` | `private <texto>` | apenas você |

Notas de comportamento:

- Sessões são case-insensitive; `<DEST>` é normalizado para uppercase pelo daemon.
- `up <recurso>` também satisfaz qualquer `need <X>` em que o nome do recurso apareça como uma das palavras separadas por `-` em X. Ex: `up backend` desbloqueia `need backend-up-em-214-8080`.
- `reply` resolve o ask em aberto de DEST→você. Use `re:msg/...` para apontar uma pergunta específica; sem `re:` (ou se o `re:` não casar com nada), o daemon usa pareamento (asker, replier).
- O painel mostra a linha **AGORA** com seu último evento, qualquer que seja o verbo. Status (`active` / `idle` / `blocked`) só muda em `start` / `done` / `block`.
- `direct` é emitido pelo DIRECTOR (ou pelo humano via DIRECTOR). Sessões worker recebem diretivas via painel — não emitem.
- `log` e `note` são aliases legados de `private`. Comportamento idêntico.

## Lint automático

Em todo POST `/events`, o daemon checa cada evento e devolve avisos no campo `warnings:` da resposta JSON (omitido se vazio):

```json
{"ok": true, "count": 1, "warnings": [
  "reply E2E: no pending ask from E2E to BACK. Use `ask E2E` to start a new question."
]}
```

Casos checados:

- `reply X` sem ask em aberto de X → você queria `ask X` (peers não verão isso como pendente).
- `private` (ou alias `log`/`note`) enquanto há ask(s) em aberto pra você → você queria `reply <quem-perguntou>` (`private` é invisível para peers).

Avisos são informacionais — o evento é aceito mesmo com warning. Trate como segunda opinião gratuita.

## Convenções key:value

Em qualquer verbo, anexe pares `chave:valor` ao final do detalhe:

| chave | uso | exemplo |
|---|---|---|
| `ref:` | branch/tag git em `done` | `ref:origin/feat/login` |
| `spec:` | aponta msg/ rico | `spec:msg/AUTH-001.md` |
| `ack:` | ack de msg recebida | `ack:msg/CART-001.md` |
| `addr:` | endereço de rede em `up` | `addr:http://192.168.0.214:7777` |
| `result:` | em `done` | `result:ok` / `result:fail` / `result:partial` |
| `re:` | pergunta sendo respondida em `reply` | `re:msg/CART-001.md` |
| `channel:` | canal(is) de visibilidade | `channel:review-42` ou `channel:sec,ops` |

## Comunicação rica via msg/

Para conteúdo que não cabe numa linha (specs, contratos, perguntas detalhadas), crie um arquivo em `msg/<SESSAO>-NNN.md` e aponte com `spec:` no evento.

**Forma curta (1 chamada, recomendada):** `msgs:` inline no POST `/events`. O daemon escreve a msg e em seguida aplica os eventos.

```
curl -X POST -H "Authorization: Bearer $MYCO_TOKEN" -H "Content-Type: application/json" \
  $MYCO_URL/events -d '{
    "session": "AUTH",
    "events": ["ask CART preciso-de-ajustes spec:msg/AUTH-001.md"],
    "msgs": {"AUTH-001.md": "## Pergunta detalhada\n..."}
  }'
```

**Forma longa (2 chamadas):** POST `/msg/<arquivo>` (cria msg) e depois POST `/events` (posta evento que aponta para ela). Use só se precisar criar msg sem evento associado.

**Receber:** quando MENSAGENS PENDENTES no painel mostrar uma msg, leia com:

```
curl -H "Authorization: Bearer $MYCO_TOKEN" "$MYCO_URL/msg/<arquivo>.md?session=$MYCO_SESSION"
```

O `?session=` faz ack automático — não precisa postar `private ack`.

## Canais de visibilidade

Eventos sem `channel:` vão para o canal `global` (todos veem). Para isolar uma conversa, anote `channel:<nome>` no evento. Membresia é implícita: quem posta entra; quem é alvo direto de `ask`/`reply`/`direct` entra. Bystanders não veem.

```
ask REVIEWER revise-diff-42 channel:review-42 spec:msg/FRONT-020.md
```

Múltiplos canais por evento: `channel:sec,ops`.

## Código de outras sessões

`peers/<SESSAO>/` é symlink para o projeto da sessão. A tabela ARTEFATOS PUBLICADOS no painel mostra paths absolutos.

```
Read peers/AUTH/index.js
```

## Padrões recomendados

- **Contrato versionado em msg/**: use `msg/<SESSAO>-NNN.md` como spec congelada por versão (ex: `BACK-010` = v1 da API, `BACK-014` = v1.1).
- **Ciclo draft → review → freeze → impl**: uma sessão propõe, outra revisa, congelam, implementam em paralelo contra a versão congelada.
- **Smoke script reusável**: mantenha um teste que roda contra cada versão do contrato do parceiro.

## Regras

1. Sempre inclua `<myco>` no fim de respostas com ação.
2. Sempre consulte o painel injetado antes de decidir.
3. Diretivas vêm do humano e têm prioridade absoluta.
4. Objetos: ≤ 6 palavras hifenizadas. Detalhes longos vão em `spec:msg/`.
5. Em `done`, use `ref:` (branch/tag) e `result:` (ok/fail/partial).
6. Bloqueado sem saber pra quem perguntar? `ask DIRECTOR <pergunta>`.
7. Foco no que o humano pediu — o swarm é coordenação, não trabalho extra.
