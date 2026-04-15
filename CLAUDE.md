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
- `done <objeto>` — terminei X (use `ref:` e `spec:` para detalhes)
- `need <objeto>` — preciso de X (de outra sessão)
- `block <motivo>` — estou bloqueado
- `up <recurso>` / `down <recurso>` — recurso subiu/caiu
- `ask <destinatário> <pergunta>` — pergunta dirigida (use `spec:` para specs ricas)
- `reply <destinatário> <resposta>` — resposta a uma pergunta (use `spec:` para detalhes)
- `note <texto>` — observação interna (ATENÇÃO: `note` NÃO é visível para outras sessões! Use `reply` para responder perguntas)

## Comunicação entre sessões

### Perguntar
```
<myco>
ask AUTH preciso-de-ajustes spec:msg/CART-001.md
</myco>
```

### Responder (IMPORTANTE: use reply, não note)
```
<myco>
reply CART resposta-sobre-ajustes spec:msg/AUTH-002.md
</myco>
```

`reply` é visível ao destinatário e limpa a pergunta de PERGUNTAS PENDENTES. `note` é invisível para outras sessões — só serve para registros internos.

### Confirmar recebimento
```
<myco>
note ack ack:msg/CART-001.md
</myco>
```

## Convenções key:value

Eventos suportam pares `chave:valor` opcionais no campo de detalhe:

| chave | significado | exemplo |
|---|---|---|
| `ref:` | referência git (branch, tag) | `ref:origin/feat/login` |
| `spec:` | spec, contrato ou mensagem rica em msg/ | `spec:msg/AUTH-001.md` |
| `ack:` | acuso de recebimento | `ack:msg/CART-001.md` |

## Comunicação rica via msg/

Mensagens ricas são arquivos markdown trocados via HTTP pelo daemon.

### Enviar uma mensagem

1. **Crie via HTTP**: `curl -X POST -H "Authorization: Bearer $MYCO_TOKEN" -d "conteúdo" $MYCO_URL/msg/SUASESSAO-001.md`
2. **Referencie no `<myco>` block**: `ask DESTINO pergunta spec:msg/SUASESSAO-001.md`

### Receber uma mensagem

Quando a seção **MENSAGENS PENDENTES** da sua view mostrar uma mensagem:

1. **Leia via HTTP**: `curl -H "Authorization: Bearer $MYCO_TOKEN" $MYCO_URL/msg/ARQUIVO.md`
2. **Confirme leitura** no `<myco>` block: `note ack ack:msg/ARQUIVO.md`

## Acessar código de outras sessões

O diretório `peers/` no seu projeto contém symlinks para os projetos das outras sessões. Para ler código da sessão AUTH:

```
Read peers/AUTH/index.js
```

A tabela de ARTEFATOS PUBLICADOS mostra o path de cada sessão para referência.

## Regras

1. Sempre inclua `<myco>` block no final de respostas com ações
2. Sempre consulte o painel injetado antes de decidir
3. Se bloqueado, use `ask DIRECTOR <pergunta>`
4. Respeite as diretivas do painel — vêm do humano, prioridade absoluta
5. Foque no trabalho que o humano pedir — o swarm é só coordenação
6. Use `ref:` no `done` quando tiver uma branch/tag para publicar
7. Use `msg/` para specs detalhadas, não tente enfiar tudo numa linha
8. **Use `reply` para responder perguntas, NUNCA `note`** — note é invisível para outras sessões
