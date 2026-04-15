# Protocolo v1

Especificação do protocolo de coordenação myco.

## Layout do swarm

```
/tmp/myco-swarm/           (ou qualquer diretório)
├── log/
│   ├── FRONT.log          # só FRONT escreve (via daemon)
│   ├── BACK.log           # só BACK escreve (via daemon)
│   ├── AUTH.log           # só AUTH escreve (via daemon)
│   └── DIRECTOR.log       # humano + sessão conselheira
├── view/
│   ├── FRONT.md           # daemon escreve, FRONT recebe via hook
│   ├── BACK.md            # daemon escreve, BACK recebe via hook
│   ├── AUTH.md            # daemon escreve, AUTH recebe via hook
│   └── DIRECTOR.md        # daemon escreve, DIRECTOR lê
└── msg/
    ├── FRONT-001.md       # mensagens ricas entre sessões
    └── BACK-001.md
```

**Regra de ouro**: cada arquivo tem exatamente um escritor.

- O daemon escreve em `log/*.log` (via HTTP POST ou filesystem append)
- O daemon escreve em `view/*.md` (escrita atômica via rename)
- Sessões escrevem em `msg/*.md` (via HTTP POST, imutáveis)

## Formato de log

Uma linha = um evento. Texto puro.

```
<timestamp> <sessão> <verbo> <objeto> [<detalhes>]
```

Exemplos:

```
2026-04-14T10:23:14 FRONT start login.endpoint
2026-04-14T10:23:15 BACK need AUTH.auth.v2
2026-04-14T10:23:20 AUTH done auth.v2 ref:origin/feat/new-auth
2026-04-14T10:23:22 FRONT ask DIRECTOR preciso-de-specs spec:msg/FRONT-001.md
2026-04-14T10:23:45 DIRECTOR direct all usar-JWT-HS256
2026-04-14T10:24:00 AUTH reply BACK resposta-sobre-contrato spec:msg/AUTH-002.md
2026-04-14T10:24:10 FRONT say vou-reiniciar-o-banco-em-1min
```

## Verbos

| Verbo | Significado | Exemplo |
|---|---|---|
| `start` | comecei a trabalhar em X | `start login.endpoint` |
| `done` | terminei X, efeito publicado | `done auth.v2 result:ok ref:origin/feat/new-auth` |
| `need` | declaro dependência (precondição) | `need AUTH.auth.v2` |
| `block` | estou bloqueado | `block esperando-deploy-do-db` |
| `up` | recurso subiu (suporta `addr:`) | `up dev-server addr:http://192.168.0.214:7777` |
| `down` | recurso caiu | `down endpoint /api/auth` |
| `ask` | pergunta dirigida a outra sessão | `ask DIRECTOR preciso-de-specs` |
| `reply` | resposta a uma pergunta | `reply BACK resposta re:msg/BACK-005.md spec:msg/AUTH-002.md` |
| `say` | broadcast visível para TODAS as sessões | `say deploy-em-1min` |
| `direct` | diretiva (só DIRECTOR usa) | `direct all usar-JWT-HS256` |
| `log` | observação interna (invisível para outros) | `log ack ack:msg/CART-001.md` |

> `note` é aceito como alias de `log` por compatibilidade.

### Semântica especial

- **`ask`**: self-ask é rejeitado (target == sender → ignorado pelo daemon)
- **`reply`**: resolve perguntas pendentes do target→sender. Com `re:`, resolve apenas a pergunta específica. Sem `re:`, resolve todas as pendentes do par.
- **`say`**: aparece na seção BROADCASTS de todas as views
- **`log`** (alias: `note`): NUNCA visível para outras sessões — só serve para registros internos e acks
- **`direct`**: aparece no topo de todas as views com prioridade máxima

## Convenções key:value

Eventos suportam pares `chave:valor` opcionais no campo de detalhe:

| Chave | Significado | Exemplo |
|---|---|---|
| `ref:` | referência git (branch, tag) | `ref:origin/feat/login` |
| `spec:` | spec, contrato ou mensagem rica em msg/ | `spec:msg/AUTH-001.md` |
| `ack:` | acuso de recebimento | `ack:msg/CART-001.md` |
| `addr:` | endereço de rede (URL, host:port) | `addr:http://192.168.0.214:7777` |
| `result:` | resultado de execução | `result:ok`, `result:fail`, `result:partial` |
| `re:` | referência à pergunta sendo respondida | `re:msg/FRONT-010.md` |

Exemplo completo:

```
done auth-api-v2 result:ok ref:origin/feat/new-login spec:msg/AUTH-003.md
reply FRONT resposta re:msg/FRONT-010.md spec:msg/DIRECTOR-005.md
```

## Convenções de slug

O campo `<objeto>` nos verbos deve ser curto e legível:

- **Máximo 6 palavras hifenizadas** (ex: `login-endpoint`, `auth-api-v2`, `db-migration-users`)
- Detalhes longos vão em `spec:msg/` — não no objeto
- Evitar handles como `servidor-nao-alcancavel-do-meu-sandbox-localhost-7777` — use `servidor-inalcancavel` e detalhe em spec

## Mensagens ricas (msg/)

Para comunicação que não cabe numa linha de evento, sessões trocam arquivos markdown via HTTP.

### Enviar

```bash
curl -X POST -H "Authorization: Bearer $MYCO_TOKEN" \
  -d "conteúdo da mensagem" \
  $MYCO_URL/msg/SUASESSAO-001.md
```

Depois, referencie no bloco `<myco>`:

```
ask DESTINO pergunta-sobre-contrato spec:msg/SUASESSAO-001.md
```

### Receber

Quando a seção **MENSAGENS PENDENTES** da view mostrar uma mensagem:

```bash
curl -H "Authorization: Bearer $MYCO_TOKEN" \
  "$MYCO_URL/msg/ARQUIVO.md?session=$MYCO_SESSION"
```

O parâmetro `?session=` faz ack automático — a mensagem sai de pendentes na próxima renderização.

### Regras de msg/

- Mensagens são **imutáveis**: POST em arquivo existente retorna 409
- Tamanho máximo: **64KB** (413 em excesso)
- Tags perigosas (`<system-reminder>`, `<command-*>`, etc.) são sanitizadas na leitura
- Convenção de nomes: `SESSAO-NNN.md` (ex: `FRONT-001.md`, `AUTH-002.md`)

## Como sessões se comunicam

### Escrevendo eventos — blocos `<myco>`

Sessões NÃO escrevem diretamente em arquivos de log. Em vez disso, Claude inclui um bloco no texto da resposta:

```
<myco>
start login.endpoint
need AUTH.auth.v2
</myco>
```

Um **Stop hook** (`myco-hook.py`) captura este bloco do transcript e envia os eventos ao daemon via HTTP POST. Se HTTP falhar, faz fallback para append no filesystem.

Regras do bloco:
- Uma linha = um evento
- Formato: `<verbo> <obj> [detail...]`
- Linhas em branco e comentários (`# ...`) são ignorados
- Se houver vários blocos `<myco>` no mesmo turno, **o último ganha**
- Linhas com verbo desconhecido são silenciosamente ignoradas

### Recebendo contexto — injeção automática

Um **hook UserPromptSubmit** (`myco_prompt_hook.py`) injeta a view da sessão como `additionalContext` a cada prompt. A sessão nunca precisa fazer Read tool calls para consultar o swarm — o contexto chega sozinho.

A view é obtida via HTTP GET `/view/{SESSION}`, com fallback para renderização local via filesystem.

## Formato de view

Markdown estruturado, gerado pelo daemon, personalizado por sessão:

```markdown
<!-- myco protocol v1 -->
# myco view — FRONT

## AGORA
Status: **active** — start login.endpoint
Nenhum bloqueador conhecido.

## DIRETIVAS
- [2026-04-14T10:23:45] usar-JWT-HS256

## ARTEFATOS PUBLICADOS
| sessão | artefato | ref | result | path | spec |
|---|---|---|---|---|---|
| AUTH | auth.v2 | origin/feat/new-auth | ok | /home/user/auth | — |

## SEUS BLOQUEADORES
Nenhum.

## SEUS DEPENDENTES
- BACK

## BROADCASTS
- [2026-04-14T10:24:10] **AUTH**: deploy-db-em-1min

## PEERS
- **BACK**: active, last-seen 4s
- **AUTH**: idle, last-seen 12s

## RECURSOS COMPARTILHADOS
| recurso | estado | endereço |
|---|---|---|
| container iam-db | UP | — |

## EVENTOS RELEVANTES (últimos 15)
...

## PERGUNTAS PENDENTES
Nenhuma.

## MENSAGENS PENDENTES
Nenhuma mensagem pendente.
```

### View do DIRECTOR

A view do DIRECTOR é mais rica e inclui seções extras:

- **Tabela de sessões**: status, última ação, last-seen, bloqueadores, dependentes
- **Grafo de dependências**: quem espera quem
- **Conflitos detectados**: sessões trabalhando no mesmo objeto simultaneamente

### Question TTL

Perguntas expiram após **30 minutos** sem resposta. Isso evita acúmulo de perguntas stale na view.

## Regras de visibilidade

O daemon filtra eventos por sessão antes de renderizar a view:

| Tipo de evento | Visibilidade |
|---|---|
| Próprios eventos | Sempre visível |
| `direct`, `say` | Todas as sessões |
| `ask` endereçado a mim | Sempre visível |
| `reply` | Só sender e target |
| `log`/`note` com `ack:` | Só quem enviou a msg original |
| `log`/`note` de outros | Invisível (spam filter) |
| Outros eventos | Todas as sessões |

Filtro atual: **all-see-all** para eventos estruturais (start, done, need, block, up, down). Preparado para filtros mais seletivos em swarms maiores.

## Ciclo operacional

```
┌──────────────────────────────────────────────────────────┐
│ 1. Usuário digita prompt                                  │
│ 2. Hook UserPromptSubmit injeta view como contexto        │
│ 3. Claude lê o contexto injetado e decide ação            │
│ 4. Claude executa (código, testes, etc.)                  │
│ 5. Claude inclui <myco> block no final da resposta        │
│ 6. Hook Stop captura o block e envia ao daemon            │
│ 7. Daemon indexa eventos e re-renderiza views             │
│ 8. Próximo prompt de qualquer sessão recebe view fresca   │
└──────────────────────────────────────────────────────────┘
```

## Padrões recomendados

Padrões que emergiram em uso real e são recomendados:

### Contrato versionado via msg/
Use `msg/SESSAO-NNN.md` como fonte de verdade congelada por versão. Exemplo: `BACK-010.md` = v1 da API, `BACK-014.md` = v1.1. Cada mensagem é imutável — funciona como snapshot de contrato.

### Ciclo draft→review→freeze→impl
Uma sessão propõe spec (draft), outra revisa e ajusta (review), congelam a versão final (freeze), implementam em paralelo (impl). Fluxo natural para negociação de contratos HTTP/API.

### Smoke script como artefato reusável
Sessão consumidora mantém um script de testes (`smoke.sh`) que roda contra cada versão do serviço parceiro. Custo baixo, valor alto para regressão.

## Versionamento

Este documento é **protocol v1**. Cada view começa com:

```html
<!-- myco protocol v1 -->
```

Sessões podem checar a versão se quiserem adaptar comportamento.
