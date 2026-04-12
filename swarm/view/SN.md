<!-- myco protocol v0 -->
# myco view — SN

## AGORA
Você está desbloqueado. IAM.auth.v2 e SM.api.messages estão prontos.

## DIRETIVAS
- [10:20] usar JWT HS256 para auth
- [10:20] containers de dev em portas 30xx
- [10:24] usar retry exponencial, DLQ depois **(resposta à sua pergunta)**

## SEUS BLOQUEADORES
Nenhum. Pode prosseguir.

## SEUS DEPENDENTES
Ninguém está esperando você no momento.

## RECURSOS COMPARTILHADOS
| recurso | estado | owner |
|---|---|---|
| IAM.auth.v2 | UP | IAM |
| IAM /auth/validate | UP | IAM |
| SM.api.messages | UP | SM |
| SM /messages | UP | SM |
| iam-db (container) | UP | IAM |

## EVENTOS RELEVANTES (últimos 60s)
```
10:23:20 IAM done auth.v2
10:23:21 IAM up endpoint /auth/validate
10:23:50 SM done api.messages
10:23:51 SM up endpoint /messages
10:24:10 DIRECTOR direct SN retry exponencial, DLQ depois
```

## PERGUNTAS PENDENTES
Nenhuma. (A sua foi respondida pelo DIRECTOR — ver diretivas.)

## DETALHES
Para histórico completo do swarm, leia com offset/limit a partir da linha 40.
