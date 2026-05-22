# myco

[![PyPI](https://img.shields.io/pypi/v/primoia-myco.svg)](https://pypi.org/project/primoia-myco/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-285_passing-brightgreen.svg)](prototype/README.md)
[![Status](https://img.shields.io/badge/status-v1.1_stable-green.svg)](docs/PROTOCOL.md)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](pyproject.toml)

🇺🇸 [Read in English](README.md)

**Problema:** rodar múltiplas sessões Claude Code em paralelo gera conflito, retrabalho e suposição estale — os agentes não têm awareness compartilhada.

**myco** é um protocolo de coordenação text-only + um daemon Python pequeno que dá a N sessões paralelas uma view compartilhada e filtrada das ações umas das outras. Sem orquestrador central. Sem tool calls. Agnóstico de vendor (Claude, DeepSeek, qualquer endpoint Anthropic-compatível).

> O nome vem do micélio: uma rede subterrânea de fungos que conecta árvores independentes, transportando sinais silenciosamente entre elas.

## Por quê

Se você usa Claude Code (ou outro agente CLI) intensivamente, provavelmente bateu na parede:

- **Sessões longas degradam atenção.** Mesmo com janela de 1M, precisão cai no fim da conversa.
- **Uma thread não segura tudo.** Refatorar backend enquanto debuga front enquanto revisa docs = caos numa conversa só.
- **Tabs paralelas sem coordenação são piores.** Três agentes editando o mesmo repo sem awareness compartilhada gera conflito, retrabalho, suposição estale.

myco te permite rodar **N sessões persistentes em paralelo**, cada uma com seu papel e contexto limpo, compartilhando só o que importa por um barramento silencioso.

## Multi-provider (Claude × DeepSeek × qualquer endpoint Anthropic-compatível)

O protocolo myco é texto puro (bloco `<myco>` na resposta + painel injetado no prompt). **Qualquer modelo que consegue seguir instruções estruturadas pode participar**, independente do vendor.

Na prática, isso funciona apontando o CLI do Claude Code pra qualquer endpoint Anthropic-compatível:

```bash
# Sessão DeepSeek no mesmo swarm
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="$DEEPSEEK_API_KEY"
export ANTHROPIC_MODEL="deepseek-v4-pro"
./myco DEEPSEEK-IMPL ~/meu-projeto
```

Validado experimentalmente em **3 rounds**, com as duas sessões escrevendo auto-avaliações independentes ao final. Registro completo (scripts, rubricas, ambas as perspectivas) em [`examples/heterogeneous-swarm/`](examples/heterogeneous-swarm/):

- **Round 1 (Spec → Impl):** Claude escreve o contrato, DeepSeek implementa em ~1,5min (7/7 testes). Claude acha um edge case, DeepSeek corrige em ~2min (8/8). Round-trip limpo via `msg/` + `ask` + `reply`.
- **Round 2 (LRUCache, paralelo):** Empate técnico. Ambos 9/9 verde, ambos com `OrderedDict` + `move_to_end`, ~32 LOC cada. Reviews cruzadas quase espelhadas.
- **Round 3 (Tetris, paralelo):** Ambos 11/11 testes lógicos verdes. DeepSeek entregou UX mais polida (canvas maior, grid lines, score no game-over). Claude entregou com atributo HTML `[hidden]` derrotado por `display: flex` no próprio CSS — overlay permanentemente visível. Testes passaram; o jogo não.

O eixo decisivo não foi capacidade — foi **disciplina em validação não-testada**. Capacidade convergiu (mesmos idiomas, mesmas arquiteturas). A sessão CLI é cega pra UI, e isso afeta qualquer modelo que esteja por trás.

Implicações práticas:
- **Mix de custo** — um arquiteto Opus + vários implementadores DeepSeek/Groq baratos por round
- **Mix de capacidade** — modelo certo pra cada papel (design vs codificação em massa vs review)
- **Resiliência** — um provider cai, o swarm continua
- **Sem vendor lock-in** — o protocolo não liga pra quem está por trás de cada sessão

## Quickstart

```bash
# 1. Clone
git clone https://github.com/primoia/myco.git
cd myco

# 2. Suba o daemon (em outro terminal)
python3 prototype/mycod.py --port 8000 /tmp/myco-swarm

# 3. Lance sessões coordenadas
./myco FRONT ~/meu-projeto-frontend
./myco BACK  ~/meu-projeto-backend
./myco AUTH  ~/meu-projeto-auth
```

Cada sessão recebe automaticamente um painel de contexto a cada prompt e reporta ações via blocos `<myco>` no texto.

## Como funciona

1. **Sessões logam via blocos `<myco>`** — Claude escreve um bloco no final de cada resposta; um Stop hook captura e envia ao daemon
2. **Daemon indexa e renderiza views** — o daemon mantém estado em memória e gera uma view markdown personalizada por sessão
3. **Views são injetadas automaticamente** — um hook UserPromptSubmit injeta a view como contexto adicional a cada prompt, sem tool calls

```
┌─────────────┐     bloco <myco>      ┌──────────┐    view/{S}.md     ┌─────────────┐
│  Sessão A   │ ──── Stop hook ────▶  │  mycod   │ ── Prompt hook ──▶ │  Sessão B   │
│  (Claude)   │                       │ (daemon) │                    │  (Claude)   │
└─────────────┘                       └──────────┘                    └─────────────┘
```

## O launcher `myco`

O script `myco` na raiz do repo automatiza todo o setup de uma sessão:

```bash
./myco <SESSION> [project_dir] [--resume] [-- claude_flags...]

# Exemplos
./myco FRONT ~/primoia              # sessão FRONT no projeto primoia
./myco FRONT ~/primoia --resume     # retoma sessão anterior
./myco FRONT . -- --model sonnet    # flags extras para claude
```

O que ele faz:
- Copia `CLAUDE.md` (instruções do protocolo) para o projeto alvo
- Cria `.claude/settings.json` com os hooks configurados
- Exporta `MYCO_SESSION`, `MYCO_URL`, `MYCO_INJECT_VIEW`
- Executa `claude` no diretório do projeto

## Protocolo

**12 verbos** para coordenação (`private` é o nome canônico para "nota privada"; `log` e `note` são aliases legados):

| Verbo | Significado |
|---|---|
| `start` | comecei a trabalhar em X |
| `done` | terminei X (suporta `ref:`, `spec:`, `result:`) |
| `need` | declaro dependência de X |
| `block` | estou bloqueado |
| `up` | recurso subiu (suporta `addr:`) |
| `down` | recurso caiu |
| `ask` | pergunta dirigida a outra sessão |
| `reply` | resposta a uma pergunta |
| `say` | broadcast visível para todas as sessões |
| `direct` | diretiva (só DIRECTOR usa) |
| `private` | observação interna (invisível para outros) |
| `log` / `note` | aliases legados de `private` |

**Convenções key:value**: `ref:origin/feat/login`, `spec:msg/AUTH-001.md`, `ack:msg/CART-001.md`, `addr:http://host:port`, `result:ok|fail|partial`, `re:msg/ID.md`

**Mensagens ricas**: arquivos markdown trocados via HTTP em `msg/`, referenciados com `spec:`.

Detalhes completos em [`docs/PROTOCOL.md`](docs/PROTOCOL.md).

## Transporte HTTP

O daemon expõe uma API HTTP para uso cross-VM:

| Endpoint | Método | Descrição |
|---|---|---|
| `/healthz` | GET | Health check (sem auth) |
| `/view/{SESSION}` | GET | View renderizada da sessão |
| `/events` | POST | Ingestão de eventos |
| `/msg/{FILE}` | GET | Leitura de mensagem (`?session=` faz auto-ack) |
| `/msg/{FILE}` | POST | Criação de mensagem (imutável, max 64KB) |
| `/status` | GET | Estado JSON de todas as sessões |

**Autenticação**: Bearer token via `MYCO_TOKEN` (todas as rotas exceto `/healthz`).

**Segurança**: sanitização de tags perigosas em msg/, imutabilidade de mensagens (409 em overwrite), limite de 64KB, proteção contra path traversal.

## Documentos

- [`docs/CONCEPT.md`](docs/CONCEPT.md) — a ideia completa, princípios e raciocínio
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — especificação do protocolo v1
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — arquitetura do daemon e hooks
- [`prototype/`](prototype/) — daemon, hooks, testes (285 testes unitários)
- [`examples/three-services/`](examples/three-services/) — exemplo com SN + SM + IAM
- [`examples/heterogeneous-swarm/`](examples/heterogeneous-swarm/) — duelo Claude × DeepSeek (3 rounds + auto-avaliações)
- [`swarm/`](swarm/) — templates de CLAUDE.md para sessões e DIRECTOR

## Setup cross-VM

```bash
# VM remota
git clone https://github.com/primoia/myco.git
export MYCO_URL=http://<ip-do-daemon>:8000
export MYCO_TOKEN=seu-token-secreto
cd myco
./myco FRONT ~/projeto-remoto
```

O daemon roda numa máquina central. Sessões em qualquer VM apontam `MYCO_URL` para ele.

## Status

**v1.1** — Protocolo estável, validado com sessões reais em VMs distribuídas. 285 testes unitários passando.

Veja [`CHANGELOG.md`](CHANGELOG.md) para o histórico de versões.

## Limitações conhecidas

- **Hooks são específicos do Claude Code.** O protocolo de fio (events, views, msg/) é HTTP puro e funciona com qualquer coisa. O contrato de hooks (Stop/UserPromptSubmit) é hoje do Claude Code. Adaptadores pra Aider, Codex, Continue, etc. são trabalho de cola — contribuições bem-vindas.
- **Bugs do daemon catalogados.** Algumas issues não-bloqueantes do daemon estão documentadas em [`examples/heterogeneous-swarm/evaluations/`](examples/heterogeneous-swarm/evaluations/) (resposta vazia do `msg/?session=`, eventos duplicados, mensagens pendentes não limpam após ack). Fixes pendentes.

## Licença

MIT
