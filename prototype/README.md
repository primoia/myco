# myco — Daemon e hooks (Python)

Implementação completa do protocolo myco v1. Daemon, hooks Claude Code, e suite de testes.

## Componentes

| Arquivo | Descrição |
|---|---|
| `mycod.py` | Daemon: polling + HTTP server + SwarmIndex + renderer (~1000 linhas) |
| `myco-hook.py` | Stop hook: captura `<myco>` blocks → POST /events no daemon |
| `myco_prompt_hook.py` | UserPromptSubmit hook: injeta view como additionalContext |
| `myco_view.py` | Biblioteca + CLI para renderizar views on-demand |
| `test_v1.py` | Suite de testes: **224 testes** cobrindo toda a funcionalidade |

## Como rodar o daemon

```bash
# Porta padrão 8000; o daemon é sempre multi-channel.
python3 mycod.py /tmp/myco-swarm

# Porta customizada
python3 mycod.py --port 9000 /tmp/myco-swarm

# Modo silencioso (sem output de debug)
python3 mycod.py -q /tmp/myco-swarm
```

Autenticação:
- Toda requisição (exceto `/healthz`) precisa de `Authorization: Bearer <token>`.
- O SHA256 do token identifica o canal; canais são completamente isolados.
- Tokens precisam atender os requisitos mínimos de força (≥ 32 chars, ≥ 80 bits de entropia) no momento em que o canal é criado.
- Gere um token com `openssl rand -hex 24` ou similar.

O daemon:
- Cria um subdiretório por canal em `<swarm_dir>/channels/<sha256>/`
- Dentro de cada canal: `log/`, `view/`, `msg/`
- Roda HTTP server em thread background + poll loop em thread principal
- Re-renderiza views a cada mudança detectada
- Reconstrói estado completo do zero no restart (stateless, canais são re-lidos do disco)
- Auto-registra uma sessão no primeiro `GET /view/<SESSAO>`: a sessão passa a existir no momento em que pede a própria view, sem precisar publicar nada primeiro.

## Como rodar os testes

```bash
cd prototype
python3 -m pytest test_v1.py -v
```

224 testes cobrindo:

- Parsing de eventos e key:value
- SwarmIndex (status, needs/provides, blockers, dependents)
- Rendering de views (worker, DIRECTOR, filtros de visibilidade)
- HTTP endpoints (events, view, msg, healthz, status, dispatch)
- Autenticação (Bearer token)
- Modo híbrido (HTTP + filesystem coexistindo)
- Mensagens ricas (msg/ GET/POST, auto-ack, imutabilidade, size limit)
- Segurança (tag sanitization, path traversal, self-ask)
- Verbos: say (broadcast), ask/reply, note, direct
- Question TTL (expiração após 30min)
- Last-seen timestamps

## Requisitos

- Python 3.8+
- Sem dependências externas (usa só stdlib)
- `pytest` para rodar os testes

## Como sessões se conectam

Sessões não precisam de setup manual. O launcher `myco` (na raiz do repo) faz tudo:

```bash
# Na raiz do repo myco
./myco FRONT ~/meu-projeto
```

Para setup manual (raro):

```bash
export MYCO_SESSION=FRONT
export MYCO_URL=http://localhost:8000
export MYCO_TOKEN=$(openssl rand -hex 24)  # obrigatório
export MYCO_INJECT_VIEW=1
```

> Quando `MYCO_URL` está definido, os hooks tratam o daemon HTTP como fonte
> única de verdade — não há fallback para um swarm local. Um daemon
> inacessível ou um token rejeitado resulta em "view vazia", nunca em
> "view misturada com outro swarm".

## Arquivos de validação histórica

| Arquivo | Descrição |
|---|---|
| `EXPERIMENT.md` | Experimento de injeção vs indução (condições A-F) |
| `RESULTS.md` | Resultados da validação Fase 0 (latência, concorrência) |
| `HOOK-VALIDATION.md` | Validação do Stop hook |
