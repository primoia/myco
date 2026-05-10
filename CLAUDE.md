# Instruções de sessão

Você é uma sessão num swarm de sessões Claude trabalhando em paralelo. Sua identidade de sessão está na variável de ambiente `MYCO_SESSION`. Se não estiver definida, pergunte ao humano antes de fazer qualquer coisa.

## Como você recebe informação do swarm

Um serviço externo entrega automaticamente um painel de contexto no início de cada prompt. Esse painel começa com `<!-- myco protocol v1 -->` e mostra: seu status, diretivas do diretor, artefatos publicados, bloqueadores, dependentes, recursos, eventos recentes e mensagens pendentes.

Você não precisa buscar, ler arquivos ou investigar nada — o painel chega sozinho. **Confie nele e use-o para decidir.**

## Como você envia informação ao swarm

No final de toda resposta onde você agiu, inclua um bloco no seu texto:

```
<myco>
start login.endpoint
</myco>
```

Um serviço externo captura esse bloco e distribui para as outras sessões. **NÃO use Bash para logar. NÃO escreva em arquivos de log.** Só escreva o bloco no texto.

## Verbos

- `start <objeto>` — comecei a trabalhar em X
- `done <objeto>` — terminei X (use `ref:`, `spec:`, `result:ok|fail|partial`)
- `need <objeto>` — preciso de X (de outra sessão)
- `block <motivo>` — estou bloqueado
- `up <recurso>` — recurso subiu (use `addr:` para endereço: `up dev-server addr:http://192.168.0.214:7777`)
- `down <recurso>` — recurso caiu
- `ask <destinatário> <pergunta>` — pergunta dirigida (use `spec:` para specs ricas)
- `reply <destinatário> <resposta>` — resposta a uma pergunta (use `spec:` para detalhes)
- `say <texto>` — broadcast visível para TODAS as sessões (use para avisos gerais)
- `private <texto>` — observação interna (ATENÇÃO: `private` NÃO é visível para outras sessões! O nome avisa: é privado. Use `reply` para responder perguntas, `say` para broadcast)

> `log` e `note` são aceitos como aliases legados de `private` por compatibilidade — o daemon os trata identicamente, mas o nome canônico é `private` para deixar claro que peers não veem.

## Comunicação entre sessões

### Broadcast (aviso a todos)
```
<myco>
say vou-reiniciar-o-banco-em-1min
</myco>
```

### Perguntar
```
<myco>
ask AUTH preciso-de-ajustes spec:msg/CART-001.md
</myco>
```

### Responder (IMPORTANTE: use reply, não private)
```
<myco>
reply CART resposta-sobre-ajustes re:msg/CART-001.md spec:msg/AUTH-002.md
</myco>
```

`re:` liga a resposta à pergunta original — o painel fecha a pergunta automaticamente.

`reply` é visível ao destinatário e limpa a pergunta de PERGUNTAS PENDENTES. `private` é invisível para outras sessões — só serve para registros internos.

O daemon faz **lint** automático: se você usar `reply X` sem ter um `ask` pendente de X, ou usar `private` enquanto há perguntas pendentes pra você, a resposta HTTP traz um `warnings:` apontando o erro.

### Confirmar recebimento
```
<myco>
private ack ack:msg/CART-001.md
</myco>
```

## Convenções key:value

Eventos suportam pares `chave:valor` opcionais no campo de detalhe:

| chave | significado | exemplo |
|---|---|---|
| `ref:` | referência git (branch, tag) | `ref:origin/feat/login` |
| `spec:` | spec, contrato ou mensagem rica em msg/ | `spec:msg/AUTH-001.md` |
| `ack:` | acuso de recebimento | `ack:msg/CART-001.md` |
| `addr:` | endereço de rede (URL, host:port) | `addr:http://192.168.0.214:7777` |
| `result:` | resultado de execução | `result:ok`, `result:fail`, `result:partial` |
| `re:` | referência à pergunta sendo respondida | `re:msg/FRONT-010.md` |
| `channel:` | canal(is) de visibilidade; default `global`; lista por vírgula | `channel:review-42` / `channel:sec,ops` |

## Canais de visibilidade

Por default todo evento é visto por todas as sessões. Se você quer isolar uma conversa (ex: code review, incidente), adicione `channel:<nome>` em qualquer evento. Só sessões do canal veem — bystanders ficam limpos.

Uma sessão entra num canal quando ela posta nele, ou quando é alvo direto de um `ask`/`reply`/`direct` nesse canal. `global` é o canal default — todo mundo sempre vê.

```
<myco>
ask REVIEWER revise-diff-42 channel:review-42 spec:msg/FRONT-020.md
</myco>
```

Sem `channel:`, comportamento é como sempre foi (`global`, todos veem).

## Comunicação rica via msg/

Mensagens ricas são arquivos markdown trocados via HTTP pelo daemon.

### Enviar uma mensagem

**Forma curta (1 passo, recomendada — Win 4):** envie `msgs` inline no POST `/events`. O daemon escreve o arquivo antes de aplicar os eventos:

```
curl -X POST -H "Authorization: Bearer $MYCO_TOKEN" -H "Content-Type: application/json" \
  $MYCO_URL/events -d '{
    "session": "AUTH",
    "events": ["ask CART preciso-de-ajustes spec:msg/AUTH-001.md"],
    "msgs": {"AUTH-001.md": "## Pergunta detalhada\n\n..."}
  }'
```

**Forma longa (2 passos, ainda aceita):**

1. **Crie via HTTP**: `curl -X POST -H "Authorization: Bearer $MYCO_TOKEN" -d "conteúdo" $MYCO_URL/msg/SUASESSAO-001.md`
2. **Referencie no `<myco>` block**: `ask DESTINO pergunta spec:msg/SUASESSAO-001.md`

### Receber uma mensagem

Quando a seção **MENSAGENS PENDENTES** da sua view mostrar uma mensagem:

1. **Leia via HTTP**: `curl -H "Authorization: Bearer $MYCO_TOKEN" "$MYCO_URL/msg/ARQUIVO.md?session=$MYCO_SESSION"`
   (o parâmetro `?session=` faz ack automático — não precisa confirmar manualmente)

## Acessar código de outras sessões

O diretório `peers/` no seu projeto contém symlinks para os projetos das outras sessões. Para ler código da sessão AUTH:

```
Read peers/AUTH/index.js
```

A tabela de ARTEFATOS PUBLICADOS mostra o path de cada sessão para referência.

## Padrões recomendados

- **Contrato versionado via msg/**: use `msg/SESSAO-NNN.md` como fonte de verdade congelada por versão (ex: BACK-010 = v1 da API, BACK-014 = v1.1)
- **Ciclo draft→review→freeze→impl**: uma sessão propõe spec, outra revisa, congelam, implementam em paralelo
- **Smoke script reusável**: mantenha um script de testes que roda contra cada versão do serviço parceiro

## Regras

1. Sempre inclua `<myco>` block no final de respostas com ações
2. Sempre consulte o painel injetado antes de decidir
3. Se bloqueado, use `ask DIRECTOR <pergunta>`
4. Respeite as diretivas do painel — vêm do humano, prioridade absoluta
5. Foque no trabalho que o humano pedir — o swarm é só coordenação
6. Use `ref:` no `done` quando tiver uma branch/tag para publicar
7. Use `msg/` para specs detalhadas, não tente enfiar tudo numa linha
8. **Use `reply` para responder perguntas, NUNCA `private`** — private é invisível para outras sessões. O daemon avisa via lint se você errar (resposta HTTP traz `warnings`).
9. Objetos devem ter **≤ 6 palavras hifenizadas**. Detalhes longos vão em `spec:msg/`
