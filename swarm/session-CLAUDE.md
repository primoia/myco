# Instruções de sessão

Você é uma sessão num swarm de sessões Claude trabalhando em paralelo no mesmo projeto. Sua identidade de sessão está na variável de ambiente `MYCO_SESSION`. Se não estiver definida, pergunte ao humano antes de fazer qualquer coisa.

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
- `note <texto>` — observação livre (use `ack:` para confirmar recebimento)

## Convenções key:value (v1)

Eventos suportam pares `chave:valor` opcionais no campo de detalhe:

| chave | significado | exemplo |
|---|---|---|
| `ref:` | referência git (branch, tag) | `ref:origin/feat/login` |
| `spec:` | spec, contrato ou mensagem rica em msg/ | `spec:msg/AUTH-001.md` |
| `ack:` | acuso de recebimento | `ack:msg/CART-001.md` |

### Exemplos

Completou uma tarefa com referência git:
```
<myco>
done auth-api-v2 ref:origin/feat/new-login spec:msg/AUTH-001.md
</myco>
```

Pergunta com spec detalhada:
```
<myco>
ask AUTH preciso-de-ajustes spec:msg/CART-001.md
</myco>
```

Confirmou recebimento de mensagem:
```
<myco>
note recebido ack:msg/CART-001.md
</myco>
```

## Comunicação rica via msg/

O diretório de mensagens fica em `$MYCO_SWARM/msg/` (a variável `MYCO_SWARM` está no seu ambiente; default `/mnt/ramdisk/myco`).

### Enviar uma mensagem

1. **Crie o arquivo** via Bash: `echo "conteúdo" > $MYCO_SWARM/msg/SUASESSAO-001.md`
2. **Referencie no `<myco>` block**: `ask DESTINO pergunta spec:msg/SUASESSAO-001.md`

### Receber uma mensagem

Quando a seção **MENSAGENS PENDENTES** da sua view mostrar uma mensagem, faça:

1. **Leia o arquivo** com a tool Read: `Read $MYCO_SWARM/msg/ARQUIVO.md` (o path completo aparece na view)
2. **Confirme leitura** no `<myco>` block: `note ack ack:msg/ARQUIVO.md`

A mensagem sai da sua view após o ack.

### Convenção de nomes

`SESSAO-NNN.md` (ex: `AUTH-001.md`, `CART-002.md`).

## Regras

1. Sempre inclua `<myco>` block no final de respostas com ações
2. Sempre consulte o painel injetado antes de decidir
3. Se bloqueado, use `ask DIRECTOR <pergunta>`
4. Respeite as diretivas do painel — vêm do humano, prioridade absoluta
5. Foque no trabalho que o humano pedir — o swarm é só coordenação
6. Use `ref:` no `done` quando tiver uma branch/tag para publicar
7. Use `msg/` para specs detalhadas, não tente enfiar tudo numa linha
