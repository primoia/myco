# Multi-Channel Mode (myco v1.4)

## Visão Geral

O modo multi-canal permite rodar múltiplos swarms isolados em um único daemon. Cada token único cria e acessa um "canal" completamente isolado dos demais.

**Casos de uso:**
- Múltiplos times trabalhando independentemente
- Ambientes isolados (dev/staging/prod)
- Projetos diferentes na mesma infraestrutura
- Isolamento de segurança por projeto

## Arquitetura

```
swarm_dir/
  channels/
    <sha256-do-token-alpha>/
      log/
      view/
      msg/
    <sha256-do-token-beta>/
      log/
      view/
      msg/
```

Cada canal é identificado pelo **SHA256 do token**, garantindo:
- ✅ Tokens nunca são armazenados em plaintext
- ✅ Impossível descobrir o token a partir do hash
- ✅ Isolamento total entre canais

## Segurança

### Validação de Token

Para prevenir tokens fracos (fáceis de adivinhar):

- **Comprimento mínimo:** 32 caracteres
- **Entropia mínima:** 80 bits (~16 caracteres aleatórios)
- **Padrões proibidos:** caracteres repetidos (ex: `aaaaa...`)

Exemplos:

```bash
# ✗ REJEITADO - muito curto
export MYCO_TOKEN="abc123"

# ✗ REJEITADO - baixa entropia
export MYCO_TOKEN="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

# ✓ ACEITO - comprimento e entropia adequados
export MYCO_TOKEN="myco-project-alpha-$(uuidgen)-$(date +%s)"
```

### Rate Limiting

Proteção contra brute-force de tokens:

- **Limite:** 5 tentativas falhas por IP
- **Janela:** 60 segundos
- **Cooldown:** 300 segundos (5 minutos) após bloqueio

Após 5 falhas, o IP é temporariamente bloqueado:
```json
{"ok": false, "error": "too many failed attempts, retry in 299s"}
```

### Isolamento Absoluto

Canais **nunca** compartilham dados:
- Logs separados
- Views separadas
- Mensagens separadas
- Nenhuma visibilidade cruzada

Um token **não pode** acessar dados de outro canal, mesmo conhecendo o hash.

## Uso

### Iniciar Daemon

```bash
python3 mycod.py --multi-channel --port 8000 /tmp/myco-swarm
```

Saída:
```
[mycod] multi-channel mode
[mycod] HTTP server on port 8000
[mycod] channels dir: /tmp/myco-swarm/channels
[mycod] token requirements: min 32 chars, min 80 bits entropy
```

### Configurar Sessões

**Time Alpha (canal isolado):**
```bash
export MYCO_TOKEN="myco-alpha-team-secure-token-2026-$(uuidgen)"
export MYCO_URL="http://localhost:8000"
export MYCO_SESSION="FRONTEND"
```

**Time Beta (canal completamente separado):**
```bash
export MYCO_TOKEN="myco-beta-team-secure-token-2026-$(uuidgen)"
export MYCO_URL="http://localhost:8000"
export MYCO_SESSION="BACKEND"
```

Cada time vê apenas seus próprios eventos, sem interferência.

### Health Check

```bash
curl http://localhost:8000/healthz
```

Resposta:
```json
{
  "ok": true,
  "mode": "multi-channel",
  "channels": 2
}
```

## Geração de Tokens Seguros

### Opção 1: UUID + Timestamp
```bash
export MYCO_TOKEN="myco-$(uuidgen)-$(date +%s%N)"
```

### Opção 2: OpenSSL
```bash
export MYCO_TOKEN="myco-$(openssl rand -hex 32)"
```

### Opção 3: Python
```bash
export MYCO_TOKEN=$(python3 -c "import secrets; print('myco-' + secrets.token_urlsafe(32))")
```

## Migração de Modo Single → Multi

**Antes (single-channel):**
```bash
python3 mycod.py /tmp/myco-swarm
# Todos compartilham mesmo log/view/msg
```

**Depois (multi-channel):**
```bash
python3 mycod.py --multi-channel --port 8000 /tmp/myco-swarm-multi
# Cada token = canal isolado
```

Não há migração automática. O modo multi-channel cria uma nova estrutura `channels/`.

## Troubleshooting

### "token rejected: token too short"
**Solução:** Use tokens com pelo menos 32 caracteres.

### "token rejected: token too weak (low entropy...)"
**Solução:** Use caracteres variados. Evite repetições (ex: `aaaa...`).

### "too many failed attempts, retry in XXs"
**Solução:** Aguarde o cooldown (5 min) ou corrija o token.

### Canal não aparece em /healthz
**Solução:** O canal só é criado após a primeira requisição autenticada bem-sucedida.

## Comparação: Single vs Multi

| Aspecto | Single-Channel | Multi-Channel |
|---|---|---|
| Modo de operação | Um swarm global | N swarms isolados |
| Autenticação | Token opcional único | Token obrigatório, múltiplos |
| Isolamento | Todos veem tudo | Zero visibilidade cruzada |
| Proteção brute-force | Não | Rate limiting por IP |
| Validação de token | Simples comparação | Força mínima + entropia |
| Uso de porta | Opcional | Obrigatória (HTTP) |

## Segurança: Checklist

- ✅ Use tokens com **≥32 chars** e boa entropia
- ✅ **Não compartilhe tokens** entre times/projetos
- ✅ **Não comite tokens** em repositórios (use `.env`)
- ✅ **Rode sobre TLS** em produção (nginx reverse proxy)
- ✅ **Monitore /healthz** para detectar canais inesperados
- ✅ **Limpe canais antigos** manualmente removendo `channels/<hash>/`

## Exemplo Completo

```bash
# Terminal 1: Daemon
python3 mycod.py --multi-channel --port 8000 /tmp/swarm

# Terminal 2: Time Frontend (canal Alpha)
export MYCO_TOKEN="myco-frontend-secure-$(uuidgen)-2026"
export MYCO_URL="http://localhost:8000"
export MYCO_SESSION="UI"
# Trabalhe normalmente...

# Terminal 3: Time Backend (canal Beta - isolado)
export MYCO_TOKEN="myco-backend-secure-$(uuidgen)-2026"
export MYCO_URL="http://localhost:8000"
export MYCO_SESSION="API"
# Trabalhe sem ver nada do Frontend

# Terminal 4: Verificar isolamento
curl -H "Authorization: Bearer $MYCO_TOKEN" $MYCO_URL/view/UI
# Cada token vê apenas seu próprio canal
```

## Referência de Endpoints

Todos os endpoints (exceto `/healthz`) requerem `Authorization: Bearer <token>`.

- `GET /healthz` — Status do daemon (sem auth)
- `GET /view/<SESSION>` — View da sessão no canal do token
- `POST /events` — Enviar eventos para o canal do token
- `GET /msg/<FILE>` — Ler mensagem do canal do token
- `POST /msg/<FILE>` — Criar mensagem no canal do token
- `GET /status` — Status do canal do token

**Importante:** O token no header `Authorization` determina qual canal é acessado.
