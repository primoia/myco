<!-- myco protocol v0 -->
# myco view — IAM

## AGORA
Você publicou auth.v2. SM e SN estavam esperando, ambos agora desbloqueados.

## DIRETIVAS
- [10:20] usar JWT HS256 para auth
- [10:20] containers de dev em portas 30xx

## SEUS BLOQUEADORES
Nenhum.

## SEUS DEPENDENTES
- **SM** consumiu IAM.auth.v2 (desbloqueou, já terminou sua parte)
- **SN** consumiu IAM.auth.v2 (desbloqueou)

## RECURSOS COMPARTILHADOS
| recurso | estado | owner |
|---|---|---|
| iam-db (container) | UP | IAM |
| /auth/validate | UP | IAM |

## EVENTOS RELEVANTES (últimos 60s)
```
10:23:20 IAM done auth.v2
10:23:21 IAM up endpoint /auth/validate
10:23:50 SM done api.messages
```

## PERGUNTAS PENDENTES
Nenhuma.

## PRÓXIMOS PASSOS SUGERIDOS
A feature atual (notificacao ao completar onboarding) precisa que você implemente:
- `IAM.webhook.user-events` — webhook emitido quando usuário completa onboarding

Considere começar por isso.
