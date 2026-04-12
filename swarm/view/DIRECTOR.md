<!-- myco protocol v0 -->
# myco view — DIRECTOR

## AGORA
Swarm saudável. Dois serviços publicaram artefatos-chave. SN avançou.

## ESTADO DAS SESSÕES
| sessão | estado | ação atual |
|---|---|---|
| IAM | idle | auth.v2 publicado |
| SM | idle | api.messages publicado |
| SN | ativo | implementando webhook.incoming |

## SUAS DIRETIVAS ATIVAS
- [10:20] usar JWT HS256 para auth
- [10:20] containers de dev em portas 30xx
- [10:21] feature alvo: notificacao ao completar onboarding
- [10:24] SN: usar retry exponencial, DLQ depois

## PERGUNTAS AGUARDANDO VOCÊ
Nenhuma no momento. (A última foi respondida às 10:24.)

## BLOQUEIOS ESTRUTURAIS
Nenhum. Nenhum impasse detectado.

## RECURSOS COMPARTILHADOS
| recurso | estado | owner |
|---|---|---|
| IAM.auth.v2 | UP | IAM |
| SM.api.messages | UP | SM |
| iam-db | UP | IAM |

## EVENTOS RECENTES (todos, últimos 90s)
```
10:22:10 SN start webhook.incoming
10:22:20 SN need IAM.auth.v2
10:22:22 SN block
10:22:30 SM start api.messages
10:22:45 SM need IAM.auth.v2
10:22:46 SM block
10:23:20 IAM done auth.v2
10:23:22 SM start api.messages (desbloqueado)
10:23:50 SM done api.messages
10:23:51 SM up endpoint /messages
10:23:55 SN ask DIRECTOR retry ou DLQ
10:24:10 DIRECTOR direct SN retry exponencial, DLQ depois
```

## SUGESTÕES DE INTERVENÇÃO
- Considere emitir diretiva para IAM começar a trabalhar em `IAM.webhook.user-events` (próximo bloco da feature)
