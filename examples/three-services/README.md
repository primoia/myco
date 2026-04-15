# Exemplo: three-services

Três projetos fictícios que se cruzam via API, operados por três sessões Claude em paralelo, coordenados por myco.

## Os três projetos

- **SN** — serviço de notificações (precisa chamar SM e IAM)
- **SM** — serviço de mensageria (precisa de IAM para auth)
- **IAM** — identity & access management (independente, mas fornece auth para os outros)

## Dependências naturais

```
    IAM  ──────┐
     │         │
     ▼         ▼
    SM ──────▶ SN
```

- `IAM` publica `IAM.auth.v2` → desbloqueia `SM` e `SN`
- `SM` publica `SM.api.messages` → desbloqueia `SN`
- `SN` consome ambos

## Como rodar

```bash
# Terminal 1 — daemon
python3 ~/myco/prototype/mycod.py --port 8000 /tmp/myco-swarm

# Terminal 2
~/myco/myco IAM ./IAM

# Terminal 3
~/myco/myco SM ./SM

# Terminal 4
~/myco/myco SN ./SN
```

## A feature imaginada

"Adicionar envio de notificação quando o usuário completar o onboarding."

Isso exige:

1. IAM criar um webhook `user.onboarded`
2. SM consumir o webhook e enfileirar mensagem
3. SN ler da fila e disparar a notificação

Sem myco: você media os três Claudes no olho.
Com myco: os três se coordenam via declarações no log, e você só intervém se houver impasse.
