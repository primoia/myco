# myco — Daemon e hooks (Python)

Implementação completa do protocolo myco v1. Daemon, hooks Claude Code, e suite de testes.

## Componentes

| Arquivo | Descrição |
|---|---|
| `mycod.py` | Daemon: polling + HTTP server + SwarmIndex + renderer (~1000 linhas) |
| `myco-hook.py` | Stop hook: captura `<myco>` blocks → POST /events no daemon |
| `myco_prompt_hook.py` | UserPromptSubmit hook: injeta view como additionalContext |
| `myco_view.py` | Biblioteca + CLI para renderizar views on-demand |
| `test_v1.py` | Suite de testes: **195 testes** cobrindo toda a funcionalidade |

## Como rodar o daemon

```bash
# Modo HTTP (recomendado para uso cross-VM)
python3 mycod.py --port 8000 /tmp/myco-swarm

# Com autenticação
MYCO_TOKEN=meu-token-secreto python3 mycod.py --port 8000 /tmp/myco-swarm

# Modo silencioso (sem output de debug)
python3 mycod.py --port 8000 -q /tmp/myco-swarm

# Modo filesystem-only (sem HTTP, só polling local)
python3 mycod.py /tmp/myco-swarm
```

O daemon:
- Cria `log/`, `view/`, `msg/` dentro do swarm dir
- Roda HTTP server em thread background + poll loop em thread principal
- Re-renderiza views a cada mudança detectada
- Reconstrói estado completo do zero no restart (stateless)

## Como rodar os testes

```bash
cd prototype
python3 -m pytest test_v1.py -v
```

195 testes cobrindo:

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
export MYCO_TOKEN=meu-token
export MYCO_INJECT_VIEW=1
```

## Arquivos de validação histórica

| Arquivo | Descrição |
|---|---|
| `EXPERIMENT.md` | Experimento de injeção vs indução (condições A-F) |
| `RESULTS.md` | Resultados da validação Fase 0 (latência, concorrência) |
| `HOOK-VALIDATION.md` | Validação do Stop hook |
