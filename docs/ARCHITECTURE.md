# Arquitetura

Daemon Python + hooks Claude Code. A implementação inteira vive em `prototype/`.

## Visão geral

```
┌─────────────────────────────────────────────────────────────────┐
│                          mycod.py                                │
│                                                                  │
│  ┌───────────┐   ┌────────────┐   ┌──────────────────────────┐  │
│  │  poller   │──▶│ SwarmIndex │──▶│       renderer           │  │
│  │ (1ms fs)  │   │ (memória)  │   │ (markdown personalizado) │  │
│  └───────────┘   └────────────┘   └───────────┬──────────────┘  │
│        ▲              ▲  ▲                     │                │
│        │              │  │                     ▼                │
│  log/*.log    HTTP /events              view/*.md + cache       │
│               (/msg, /view)                                     │
│                                                                  │
│  ┌───────────────────┐                                          │
│  │  HTTP server      │  ← ThreadingHTTPServer (background)      │
│  │  (porta 8000)     │                                          │
│  └───────────────────┘                                          │
└─────────────────────────────────────────────────────────────────┘
         ▲                              │
         │ POST /events                 │ GET /view/{S}
         │ POST /msg/{F}               │ GET /msg/{F}
         │                              ▼
┌─────────────────┐              ┌─────────────────┐
│   Stop hook     │              │  Prompt hook    │
│ (myco-hook.py)  │              │ (myco_prompt_   │
│                 │              │  hook.py)       │
└────────┬────────┘              └────────┬────────┘
         │ captura <myco>                 │ injeta view
         │ blocks do transcript           │ como additionalContext
         ▼                                ▼
┌──────────────────────────────────────────────────┐
│              Claude Code session                  │
│  - lê view injetada no início de cada turno       │
│  - escreve <myco> block no final de cada turno    │
└──────────────────────────────────────────────────┘
```

## Componentes

### 1. Daemon (`prototype/mycod.py`)

~1000 linhas de Python. Três responsabilidades:

**Poller** — varre `log/*.log` a cada 1ms, lê deltas via offset tracking, parseia eventos.

**SwarmIndex** — estado em memória do swarm:

```python
class SwarmIndex:
    session_status = {}        # sessão → "active"/"idle"/"blocked"
    session_action = {}        # sessão → última ação ("start login")
    needs = defaultdict(set)   # sessão → set de dependências
    provides = defaultdict(set) # sessão → set de artefatos publicados
    resources = {}             # "container iam-db" → "UP"/"DOWN"
    directives = []            # (ts, target, text)
    questions = []             # (ts, from, to, detail)
    artifacts = []             # permanentes: {ts, session, obj, ref, spec}
    broadcasts = []            # (ts, session, text) — say verb
    last_seen = {}             # sessão → timestamp
    msg_acks = defaultdict(set)    # msg_id → sessions que confirmaram
    resolved_questions = set()      # (from, to, ts) resolvidos por reply
    events = deque(maxlen=2000)     # ring buffer
```

**Renderer** — gera views markdown personalizadas por sessão. Cada sessão tem filtros de visibilidade aplicados.

**HTTP server** — `ThreadingHTTPServer` rodando em thread background:

| Endpoint | Método | Auth | Descrição |
|---|---|---|---|
| `/healthz` | GET | Não | Health check (uptime, session count) |
| `/view/{SESSION}` | GET | Sim | View renderizada (do cache em memória) |
| `/events` | POST | Sim | Ingestão de eventos (JSON: `{session, events}`) |
| `/msg/{FILE}` | GET | Sim | Leitura de mensagem (`?session=` auto-ack) |
| `/msg/{FILE}` | POST | Sim | Criação de mensagem (imutável, max 64KB) |
| `/status` | GET | Sim | Estado JSON de todas as sessões |
| `/dispatch/{SESSION}` | POST | Sim | Despacho de prompt headless |

### 2. Stop hook (`prototype/myco-hook.py`)

Disparado pelo Claude Code quando Claude termina um turno. Fluxo:

1. Recebe payload JSON via stdin (inclui `transcript_path`)
2. Lê o transcript JSONL e extrai o texto do último turno do assistant
3. Busca o último bloco `<myco>...</myco>` no texto
4. Parseia as linhas de eventos (verbo + objeto + detalhes)
5. POST `/events` no daemon via HTTP (2 tentativas, 100ms entre elas)
6. Fallback: append direto no `log/{SESSION}.log` se HTTP falhar

**Race condition handling**: o transcript pode não estar flushed quando o hook dispara. O hook faz polling por até 500ms esperando o texto do assistant aparecer.

### 3. Prompt hook (`prototype/myco_prompt_hook.py`)

Disparado pelo Claude Code antes de cada prompt do usuário. Fluxo:

1. Verifica `MYCO_INJECT_VIEW=1` (opt-in)
2. Ignora slash commands (`/clear`, `/help`, etc.)
3. GET `/view/{SESSION}` do daemon via HTTP (2 tentativas)
4. Fallback: renderiza a view localmente via `myco_view.py`
5. Imprime a view em stdout → Claude Code injeta como `additionalContext`

**Contrato**: nunca bloqueia o prompt do usuário. Qualquer erro → silent no-op.

### 4. Launcher (`myco`)

Script bash na raiz do repo. Automatiza o setup completo de uma sessão:

```bash
./myco <SESSION> [project_dir] [--resume] [-- claude_flags...]
```

O que faz:
1. Copia `CLAUDE.md` para o projeto alvo (sempre sincroniza)
2. Cria `.claude/settings.json` com os hooks apontando para o repo myco
3. Exporta `MYCO_SESSION`, `MYCO_INJECT_VIEW=1`, `MYCO_URL`
4. Executa `claude` no diretório do projeto

## Modo híbrido (HTTP + filesystem)

O daemon opera em **modo híbrido** quando `--port` é especificado:

- **Thread principal**: poll loop a 1ms no filesystem (detecta logs escritos por fallback)
- **Thread background**: HTTP server (recebe eventos via POST, serve views via GET)

Eventos recebidos via HTTP são:
1. Persistidos no `log/{SESSION}.log`
2. Processados no SwarmIndex
3. Offset do arquivo avançado (para que o poll loop não reprocesse)

Isso garante que:
- Eventos HTTP e filesystem nunca são duplicados
- Se o HTTP cair, sessões fazem fallback para filesystem
- Se alguém appenda diretamente no log, o daemon detecta no próximo poll

## Autenticação

Bearer token via variável `MYCO_TOKEN`:

- Se `MYCO_TOKEN` está definido no daemon, todas as rotas (exceto `/healthz`) exigem `Authorization: Bearer <token>`
- Se não está definido, sem autenticação (modo local)
- Hooks incluem o token automaticamente nas requests

## Segurança

- **Tag sanitization**: GET `/msg/` escapa tags perigosas (`<system-reminder>`, `<command-*>`, `<`, etc.) para prevenir prompt injection via mensagens entre sessões
- **Imutabilidade**: POST `/msg/` retorna 409 se o arquivo já existe
- **Size limit**: POST `/msg/` retorna 413 se payload > 64KB
- **Path traversal**: filenames com `/` ou `..` são rejeitados
- **Self-ask prevention**: `ask TARGET` onde target == sender é ignorado

## Stateless by design

O daemon é **stateless**. Se morrer e reiniciar:

1. Relê todos os `log/*.log` do início
2. Reconstrói o SwarmIndex completo
3. Re-renderiza todas as views

Nada é perdido. A fonte da verdade é o filesystem.

Hooks não mantêm conexões persistentes — cada prompt/turno faz requests HTTP independentes. Reinício do daemon é transparente para as sessões.

## Escrita atômica

Views são escritas via `tempfile.mkstemp` + `os.replace`:

```
1. escreve em view/.FRONT.md.xxxxx.tmp
2. os.replace(.tmp → view/FRONT.md)   ← atômico no Linux
```

Leitores nunca veem estado parcial.

## Performance

Números da validação (Fase 0, Python não otimizado):

| Métrica | Valor |
|---|---|
| Latência log→view (p50) | 1.84ms |
| Latência log→view (p99) | 2.31ms |
| 150 eventos concorrentes | 6.92ms, zero corrupção |
| RSS do daemon (ocioso) | 4.4MB |
| CPU (ocioso) | ~0% |

A latência é dominada pelo intervalo de polling de 1ms. O trabalho real (parse + index + render) é sub-millisegundo.
