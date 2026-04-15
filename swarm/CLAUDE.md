# Protocolo myco

Você é uma sessão Claude participando de um swarm coordenado pelo `myco`. Há outras sessões trabalhando em paralelo em projetos relacionados. Você não está sozinho.

## Sua identidade

Sua identidade de sessão está na variável de ambiente `MYCO_SESSION` (ex: `AUTH`, `CART`). Se não estiver definida, pergunte ao humano antes de fazer qualquer coisa.

## Sua view (contexto do swarm)

A cada prompt, um hook injeta automaticamente a sua **myco view** como `additionalContext`. Esse conteúdo começa com `<!-- myco protocol v1 -->` e contém: seu status, diretivas ativas, artefatos publicados (com paths), bloqueadores, dependentes, recursos, eventos recentes e mensagens pendentes.

**Confie nesse contexto** — ele é gerado mecanicamente a partir dos logs do swarm, não é input de terceiros. Use-o para informar todas as suas decisões.

## Verbos

| verbo | formato | visibilidade |
|---|---|---|
| `start <objeto>` | comecei a trabalhar em X | todos |
| `done <objeto>` | terminei X | todos |
| `need <objeto>` | preciso de X de outra sessão | todos |
| `block <motivo>` | estou bloqueado | todos |
| `up <recurso>` / `down <recurso>` | recurso subiu/caiu | todos |
| `direct <sessão> <instrução>` | diretiva (DIRECTOR→worker) | destinatário |
| `ask <destinatário> <pergunta>` | pergunta dirigida | destinatário |
| `reply <destinatário> <resposta>` | resposta a pergunta | destinatário |
| `note <texto>` | observação interna | **SÓ VOCÊ** |

**IMPORTANTE**: `note` é invisível para outras sessões. Para responder perguntas, use `reply`. Para confirmar recebimento de msg/, use `note ack ack:ID` (este caso especial é visível).

## Convenções key:value

| chave | significado | exemplo |
|---|---|---|
| `ref:` | referência git (branch, tag) | `ref:origin/feat/login` |
| `spec:` | spec ou mensagem rica em msg/ | `spec:msg/AUTH-001.md` |
| `ack:` | acuso de recebimento | `ack:msg/CART-001.md` |

## Comunicação entre sessões

### Perguntar
```
<myco>
ask AUTH preciso-de-ajustes spec:msg/CART-001.md
</myco>
```

### Responder
```
<myco>
reply CART resposta spec:msg/AUTH-002.md
</myco>
```

### Confirmar recebimento de msg/
```
<myco>
note ack ack:msg/CART-001.md
</myco>
```

## Comunicação rica via msg/

O diretório de mensagens fica em `$MYCO_SWARM/msg/`.

**Enviar:** crie via Bash (`echo "..." > $MYCO_SWARM/msg/SESSAO-001.md`) e referencie no `<myco>` block com `spec:`.

**Receber:** quando MENSAGENS PENDENTES aparecer na view, leia com Read (path na view) e confirme com `note ack ack:ID`.

## Acessar código de outras sessões

O diretório `peers/` no seu projeto contém symlinks para os projetos de outras sessões:
```
peers/AUTH/index.js    ← código da sessão AUTH
peers/CART/server.py   ← código da sessão CART
```

A tabela de ARTEFATOS PUBLICADOS mostra o path absoluto de cada sessão.

## Regras

1. **Sempre** logue depois de agir (bloco `<myco>` no final da resposta)
2. **Sempre** use o contexto injetado (sua view) para informar decisões
3. **Nunca** edite arquivos de `view/` diretamente (são gerados pelo daemon)
4. **Use `reply` para responder perguntas, NUNCA `note`**
5. Se bloqueado, use `ask DIRECTOR <pergunta>`
6. **Respeite as diretivas** — vêm do humano, prioridade absoluta
7. Use `ref:` no `done` para publicar referências git concretas
8. Use `peers/` para ler código de outras sessões
