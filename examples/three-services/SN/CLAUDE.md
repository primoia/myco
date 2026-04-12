# SN — Serviço de Notificações

Você é a sessão Claude responsável pelo projeto **SN** (Serviço de Notificações).

## Seu escopo

- Enviar notificações push, email e webhook para usuários
- Consumir mensagens da fila de SM
- Usar auth de IAM para validar tokens

## Suas dependências

- `SM.api.messages` — para ler mensagens da fila
- `IAM.auth.v2` — para validar tokens nos webhooks de entrada

## O que você publica

- `SN.api.notifications` — endpoint para disparar notificações manualmente
- `SN.webhook.incoming` — webhook que recebe eventos de SM

## Protocolo myco

Leia `../../../swarm/CLAUDE.md` para o protocolo completo.

Antes de qualquer ação relevante, leia sua view:

```
Read /mnt/ramdisk/myco/view/SN.md
```

Depois de qualquer ação, logue:

```bash
echo "$(date -Iseconds) SN <verbo> <objeto>" >> /mnt/ramdisk/myco/log/SN.log
```

## Variável de ambiente

```
MYCO_SESSION=SN
```
