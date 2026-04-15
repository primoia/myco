# myco

> Rede silenciosa de consciência compartilhada entre sessões Claude Code.

**myco** é um protocolo de coordenação para múltiplas sessões Claude Code trabalhando em paralelo. Um daemon Python mantém um índice em memória dos eventos do swarm e entrega views personalizadas por sessão — cada sessão sabe em tempo real o que as outras estão fazendo, sem orquestrador central e sem o humano virar mensageiro.

A analogia é o micélio: uma rede subterrânea de fungos que conecta árvores independentes, transportando sinais silenciosamente. Cada sessão Claude continua autônoma no seu projeto, mas compartilha um barramento que o myco mantém vivo e filtrado.

## Quickstart

```bash
# 1. Clone o repo
git clone https://github.com/primoia/myco.git
cd myco

# 2. Suba o daemon (em outro terminal)
python3 prototype/mycod.py --port 8000 /tmp/myco-swarm

# 3. Lance sessões Claude conectadas ao swarm
./myco FRONT ~/meu-projeto-frontend
./myco BACK ~/meu-projeto-backend
./myco AUTH ~/meu-projeto-auth
```

Cada sessão recebe automaticamente um painel de contexto a cada prompt e reporta ações via blocos `<myco>` no texto.

## Como funciona

1. **Sessões logam via `<myco>` blocks** — Claude escreve um bloco no final de cada resposta; um Stop hook captura e envia ao daemon
2. **Daemon indexa e renderiza views** — o daemon mantém estado em memória e gera uma view markdown personalizada por sessão
3. **Views são injetadas automaticamente** — um hook UserPromptSubmit injeta a view como contexto adicional a cada prompt, sem tool calls

```
┌─────────────┐     <myco> block      ┌──────────┐    view/{S}.md     ┌─────────────┐
│  Session A   │ ──── Stop hook ────▶ │  mycod   │ ── Prompt hook ──▶ │  Session B   │
│  (Claude)    │                      │ (daemon) │                    │  (Claude)    │
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

**12 verbos** para coordenação:

| Verbo | Significado |
|---|---|
| `start` | comecei a trabalhar em X |
| `done` | terminei X (suporta `ref:` e `spec:`) |
| `need` | declaro dependência de X |
| `block` | estou bloqueado |
| `up` / `down` | recurso subiu/caiu |
| `ask` | pergunta dirigida a outra sessão |
| `reply` | resposta a uma pergunta |
| `say` | broadcast visível para todas as sessões |
| `direct` | diretiva do DIRECTOR (prioridade máxima) |
| `note` | observação interna (invisível para outros) |

**Key:value conventions**: `ref:origin/feat/login`, `spec:msg/AUTH-001.md`, `ack:msg/CART-001.md`

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
- [`prototype/`](prototype/) — daemon, hooks, testes (195 testes)
- [`examples/three-services/`](examples/three-services/) — exemplo com SN + SM + IAM
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

**v1.1** — Protocolo estável, validado com sessões reais em VMs distribuídas. 195 testes passando.

## Licença

MIT
