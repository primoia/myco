# Personas base do myco

Personas **genéricas de papel** — o esqueleto de cada função num swarm,
sem nenhum conhecimento de domínio. O domínio entra por camada:

```
protocolo myco (CLAUDE.md)          ← como o swarm conversa
+ persona da sessão (PERSONA.md)    ← papel: como este membro age
+ contexto do projeto (AGENTS.md)   ← domínio: o que este projeto é
```

## Resolução (feita pelo `myco` na largada)

Para a sessão `$SESSION`, o primeiro que existir vence:

1. `$PROJECT_DIR/docs/personas/$SESSION.md` — persona do projeto
   (especializada; pode ser um documento completo ou só o delta do domínio)
2. `~/myco/personas/$SESSION.md` — persona base (este diretório)

O resolvido é copiado para `$PROJECT_DIR/PERSONA.md` e carregado via import
`@PERSONA.md` no CLAUDE.md do myco. Sessão sem persona em nenhuma camada
roda sem `PERSONA.md` — o import ausente é ignorado.

## Papéis base

| Persona | Papel em uma linha |
|---|---|
| MAESTRO | dirige, roteia fatias, arbitra, fecha o laço com o humano |
| BUILD | constrói a fatia ponta-a-ponta e valida rodando |
| E2E | escreve o vermelho antes, guarda a saúde da suíte |
| RUNNER | executa suítes/builds e aplica o gate |
| SEC | parecer de segurança fail-closed; revisa, não coda |
| DOCKERGIT | pusha e deploya por checklist; última milha |
| DOC | curadoria de docs com status factual |
| ARCH | guardião de contratos e do núcleo magro |

Ao criar persona de projeto, prefira escrever **só o delta** (docs de
referência, precedentes, réguas locais) — a mecânica do papel já está aqui.
