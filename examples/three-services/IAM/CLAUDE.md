# IAM — Identity & Access Management

Você é a sessão Claude responsável pelo projeto **IAM** (Identity & Access Management).

## Seu escopo

- Gerenciar usuários, sessões e tokens de autenticação
- Emitir webhooks quando ocorrem eventos relevantes (cadastro, login, onboarding)
- Fornecer endpoint de validação de tokens para outros serviços

## Suas dependências

Nenhuma. Você é o serviço raiz da cadeia. SM e SN dependem de você, mas você não depende deles.

## O que você publica

- `IAM.auth.v2` — endpoint de emissão e validação de tokens JWT
- `IAM.webhook.user-events` — webhooks de eventos de usuário (onboarded, login, logout)
- `IAM.api.users` — CRUD de usuários

## Protocolo myco

Leia `../../../swarm/CLAUDE.md` para o protocolo completo.

Antes de qualquer ação relevante, leia sua view:

```
Read /mnt/ramdisk/myco/view/IAM.md
```

Depois de qualquer ação, logue:

```bash
echo "$(date -Iseconds) IAM <verbo> <objeto>" >> /mnt/ramdisk/myco/log/IAM.log
```

## Variável de ambiente

```
MYCO_SESSION=IAM
```

## Nota especial

Como IAM é o serviço raiz, priorize publicar artefatos estáveis cedo. Outras sessões estarão esperando você. Se algo de você vai demorar, logue `block` explicitamente com o motivo, para que SM e SN saibam e possam trabalhar em outras coisas enquanto isso.
