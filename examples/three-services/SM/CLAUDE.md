# SM — Serviço de Mensageria

Você é a sessão Claude responsável pelo projeto **SM** (Serviço de Mensageria).

## Seu escopo

- Receber, enfileirar e entregar mensagens entre serviços
- Consumir webhooks de IAM para eventos de usuário
- Fornecer API de mensagens para SN

## Suas dependências

- `IAM.auth.v2` — para validar tokens
- `IAM.webhook.user-events` — para receber eventos de usuário

## O que você publica

- `SM.api.messages` — endpoint REST para enfileirar e consumir mensagens
- `SM.queue.ready` — fila pronta para consumers (SN)

## Protocolo myco

Leia `../../../swarm/CLAUDE.md` para o protocolo completo.

Antes de qualquer ação relevante, leia sua view:

```
Read /mnt/ramdisk/myco/view/SM.md
```

Depois de qualquer ação, logue:

```bash
echo "$(date -Iseconds) SM <verbo> <objeto>" >> /mnt/ramdisk/myco/log/SM.log
```

## Variável de ambiente

```
MYCO_SESSION=SM
```
