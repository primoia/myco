# Personas base do myco

Personas **genéricas de papel** — o esqueleto de cada função num swarm,
sem nenhum conhecimento de domínio. O domínio entra por camada:

```
protocolo myco (CLAUDE.md)          ← como o swarm conversa
+ persona da sessão (PERSONA.md)    ← papel: como este membro age
+ contexto do projeto (AGENTS.md)   ← domínio: o que este projeto é
```

## Resolução (feita pelo `myco` na largada)

**Uma fonte viva por sessão: a do projeto.** Este diretório guarda **sementes**,
que o `myco` nunca carrega diretamente:

1. Se `$PROJECT_DIR/docs/personas/$SESSION.md` não existe e há semente aqui,
   o `myco` **copia** a semente para lá na primeira largada e avisa.
2. O que entra na sessão é sempre `$PROJECT_DIR/docs/personas/$SESSION.md`.
   Dali em diante é esse arquivo que vale — edite **nele**.
3. Editar uma semente só afeta projetos que ainda não a copiaram. Se a cópia
   do projeto diverge da semente, o `myco` diz isso na largada.

Por que assim (2026-08-21): regras novas foram escritas na semente enquanto o
projeto já tinha a própria cópia; ficaram inertes por dias e nada denunciava
qual das duas estava valendo. Duas cópias com precedência silenciosa é a mesma
armadilha de dois checkouts do mesmo repo.

A resolvida é injetada **por processo** via `--append-system-prompt-file`
no `claude` da sessão — nada de arquivo de persona compartilhado em disco,
então várias sessões (MAESTRO, RUNNER, BUILD...) na MESMA pasta não colidem.
Sessão sem persona em nenhuma camada roda sem a flag.

## Papéis base

| Persona | Papel em uma linha |
|---|---|
| MAESTRO | dirige, roteia fatias, arbitra, fecha o laço com o humano |
| PLAN | traduz spec em plano técnico + ADRs propostos + tasks; bifurca, não decide |
| BUILD | constrói a fatia ponta-a-ponta e valida rodando |
| E2E | escreve o vermelho antes, guarda a saúde da suíte |
| RUNNER | executa suítes/builds e aplica o gate |
| SEC | parecer de segurança fail-closed; revisa, não coda |
| DOCKERGIT | pusha e deploya por checklist; última milha |
| DOC | curadoria de docs com status factual |
| ARCH | guardião de contratos e do núcleo magro |

A cópia do projeto nasce completa (é a semente inteira); acrescente nela o
delta do domínio (docs de referência, precedentes, réguas locais).
