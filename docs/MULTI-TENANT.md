# Multi-Tenant Mode (myco v1.6)

## Visão Geral

O daemon é sempre multi-tenant: cada token único cria e acessa um "tenant" completamente isolado dos demais. Toda requisição (exceto `/healthz`) exige `Authorization: Bearer <token>`.

**Casos de uso:**
- Múltiplos times trabalhando independentemente
- Ambientes isolados (dev/staging/prod)
- Projetos diferentes na mesma infraestrutura
- Isolamento de segurança por projeto

**Nota sobre terminologia:** até v1.5 o conceito era chamado "multi-channel" / "channel". O termo mudou para **tenant** para evitar colisão com os **canais nomeados** (`channel:<nome>`) do protocolo, que são outro conceito (rótulo de visibilidade de evento *dentro* de um tenant). Flags e strings antigas (`--multi-channel`, `--channel TOKEN`, `mode: "multi-channel"`, pasta `channels/`) continuam aceitas como aliases e são migradas automaticamente.

## Arquitetura

```
swarm_dir/
  tenants/
    <sha256-do-token-alpha>/
      log/
      view/
      msg/
    <sha256-do-token-beta>/
      log/
      view/
      msg/
```

Cada tenant é identificado pelo **SHA256 do token**, garantindo:
- ✅ Tokens nunca são armazenados em plaintext
- ✅ Impossível descobrir o token a partir do hash
- ✅ Isolamento total entre tenants

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

Tenants **nunca** compartilham dados:
- Logs separados
- Views separadas
- Mensagens separadas
- Nenhuma visibilidade cruzada

Um token **não pode** acessar dados de outro tenant, mesmo conhecendo o hash.

## Uso

### Iniciar Daemon

```bash
python3 mycod.py --port 8000 /tmp/myco-swarm
```

Saída:
```
[mycod] HTTP server on port 8000
[mycod] tenants dir: /tmp/myco-swarm/tenants
[mycod] token requirements: min 32 chars, min 80 bits entropy
```

`--multi-tenant` (ou `--multi-channel`) são aceitos como no-ops — o daemon sempre opera nesse modo.

### Configurar Sessões

**Time Alpha (tenant isolado):**
```bash
export MYCO_TOKEN="myco-alpha-team-secure-token-2026-$(uuidgen)"
export MYCO_URL="http://localhost:8000"
export MYCO_SESSION="FRONTEND"
```

**Time Beta (tenant completamente separado):**
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
  "mode": "multi-tenant",
  "tenants": 2,
  "channels": 2
}
```

(`channels` é um alias legado do mesmo valor, mantido para tooling que predata o rename.)

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

## Migração do layout on-disk (`channels/` → `tenants/`)

Se um daemon v1.6+ subir num diretório que ainda tem a pasta antiga `channels/` e não tem `tenants/`, ele renomeia automaticamente no startup. Idempotente, sem perda de dados. Tenants existentes (logs, views, msgs) permanecem intactos.

## Troubleshooting

### "token rejected: token too short"
**Solução:** Use tokens com pelo menos 32 caracteres.

### "token rejected: token too weak (low entropy...)"
**Solução:** Use caracteres variados. Evite repetições (ex: `aaaa...`).

### "too many failed attempts, retry in XXs"
**Solução:** Aguarde o cooldown (5 min) ou corrija o token.

### Tenant não aparece em /healthz
**Solução:** O tenant só é criado após a primeira requisição autenticada bem-sucedida.

## Segurança: Checklist

- ✅ Use tokens com **≥32 chars** e boa entropia
- ✅ **Não compartilhe tokens** entre times/projetos
- ✅ **Não comite tokens** em repositórios (use `.env`)
- ✅ **Rode sobre TLS** em produção (nginx reverse proxy)
- ✅ **Monitore /healthz** para detectar tenants inesperados
- ✅ **Limpe tenants antigos** manualmente removendo `tenants/<hash>/`

## Exemplo Completo

```bash
# Terminal 1: Daemon
python3 mycod.py --port 8000 /tmp/swarm

# Terminal 2: Time Frontend (tenant Alpha)
export MYCO_TOKEN="myco-frontend-secure-$(uuidgen)-2026"
export MYCO_URL="http://localhost:8000"
export MYCO_SESSION="UI"
# Trabalhe normalmente...

# Terminal 3: Time Backend (tenant Beta - isolado)
export MYCO_TOKEN="myco-backend-secure-$(uuidgen)-2026"
export MYCO_URL="http://localhost:8000"
export MYCO_SESSION="API"
# Trabalhe sem ver nada do Frontend

# Terminal 4: Verificar isolamento
curl -H "Authorization: Bearer $MYCO_TOKEN" $MYCO_URL/view/UI
# Cada token vê apenas seu próprio tenant
```

## Referência de Endpoints

Todos os endpoints (exceto `/healthz`) requerem `Authorization: Bearer <token>`.

- `GET /healthz` — Status do daemon (sem auth)
- `GET /view/<SESSION>` — View da sessão no tenant do token (auto-registra a sessão)
- `POST /events` — Enviar eventos para o tenant do token
- `GET /msg/<FILE>` — Ler mensagem do tenant do token
- `POST /msg/<FILE>` — Criar mensagem no tenant do token
- `GET /status` — Status do tenant do token

**Importante:** O token no header `Authorization` determina qual tenant é acessado.
