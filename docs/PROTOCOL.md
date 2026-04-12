# Protocolo

Especificação mínima do que uma sessão precisa saber para participar do swarm `myco`.

## Layout no ramdisk

```
/mnt/ramdisk/myco/
├── CLAUDE.md           # instruções universais (toda sessão lê no boot)
├── log/
│   ├── SN.log          # só SN escreve
│   ├── SM.log          # só SM escreve
│   ├── IAM.log         # só IAM escreve
│   └── DIRECTOR.log    # humano + sessão conselheira escrevem
└── view/
    ├── SN.md           # daemon escreve, SN lê
    ├── SM.md           # daemon escreve, SM lê
    ├── IAM.md          # daemon escreve, IAM lê
    └── DIRECTOR.md     # daemon escreve, DIRECTOR lê
```

**Regra de ouro**: cada arquivo tem exatamente um escritor.

- Sessão `X` escreve **apenas** em `log/X.log`
- Daemon escreve **apenas** em `view/*.md`
- Ninguém nunca escreve em arquivo alheio

Isso elimina 100% das condições de corrida por construção.

## Formato de log

Uma linha = um evento. Texto puro. Sem YAML, sem JSON.

```
<timestamp> <sessao> <verbo> <objeto> [<detalhes>]
```

Exemplos:

```
2026-04-11T10:23:14.123 SN start build
2026-04-11T10:23:15.007 SM need IAM.auth.v2
2026-04-11T10:23:20.441 IAM up container iam-db
2026-04-11T10:23:21.102 IAM done auth.v2
2026-04-11T10:23:22.008 SN ask DIRECTOR deve usar cache ou não
2026-04-11T10:23:45.000 DIRECTOR direct all usar JWT HS256
```

### Verbos padronizados (vocabulário inicial)

| Verbo | Significado |
|---|---|
| `start` | começou a trabalhar em algo |
| `done` | terminou algo, efeito publicado |
| `need` | declara dependência (precondição) |
| `block` | está bloqueado esperando algo |
| `up` / `down` | recurso (container, endpoint) subiu/caiu |
| `claim` | pegou tarefa pendente |
| `release` | soltou tarefa sem terminar |
| `ask` | pergunta dirigida a outra persona |
| `direct` | diretiva (só DIRECTOR usa) |
| `note` | observação livre, sem semântica de estado |

O daemon entende esses verbos para construir o índice. Qualquer outra coisa é tratada como `note`.

## Escrevendo no log

Append atômico:

```bash
echo "$(date -Iseconds) SN need IAM.auth.v2" >> /mnt/ramdisk/myco/log/SN.log
```

Como a linha é menor que 4KB e o modo é `O_APPEND`, o kernel Linux garante atomicidade entre processos. Zero lock necessário.

## Formato de view

Markdown estruturado, escrito pelo daemon, sempre com o mesmo esqueleto:

```markdown
# myco view — SN

## AGORA
<snapshot de uma linha do estado global relevante pra SN>

## DIRETIVAS
<diretivas ativas do DIRECTOR que afetam SN>

## SEUS BLOQUEADORES
<o que está impedindo SN de avançar agora>

## SEUS DEPENDENTES
<quem está esperando SN terminar algo>

## RECURSOS COMPARTILHADOS
<estado de containers, endpoints, schemas que SN usa>

## EVENTOS RELEVANTES (últimos 30s)
<lista curta, filtrada pra relevância de SN>

## PERGUNTAS PENDENTES
<perguntas de/pra SN que ainda não foram respondidas>

## DETALHES (opcional, ler com offset/limit)
<histórico mais longo, só se a sessão precisar investigar>
```

O topo cabe em 40-60 linhas. Claude lê as primeiras 80 linhas e tem consciência plena. Os detalhes ficam para o caso de investigação específica.

## Escrita atômica de view (daemon)

Para evitar que uma sessão leia uma view pela metade enquanto o daemon a reescreve, o daemon usa o padrão temp+rename:

```
1. escreve em view/SN.md.tmp
2. renomeia view/SN.md.tmp → view/SN.md  (rename() é atômico no Linux)
```

Resultado: leitores nunca veem estado parcial.

## Ciclo operacional de uma sessão

Toda sessão Claude segue este ciclo, induzido pelo `CLAUDE.md` compartilhado:

1. **Ler** `view/$EU.md` (via `Read` tool, primeiras 80 linhas)
2. **Decidir** a próxima ação com base na consciência atual
3. **Executar** a ação (escrever código, subir container, rodar testes, etc)
4. **Logar** o que fez em `log/$EU.log` (via `Bash` tool, `echo >>`)
5. Voltar ao passo 1

O daemon, em background, escuta `log/*.log` via inotify e reescreve `view/*.md` a cada mudança.

## Comunicação entre personas

### Broadcast

Qualquer evento logado é automaticamente visível (filtrado) para as outras personas na próxima leitura de view delas. Não existe "broadcast explícito" — o próprio ato de logar já é broadcast filtrado.

### Mensagem dirigida

Use o verbo `ask`:

```
2026-04-11T10:23:22 SN ask DIRECTOR deve usar cache
```

O daemon roteia isso para `view/DIRECTOR.md` na seção "PERGUNTAS PENDENTES" até que alguém responda com:

```
2026-04-11T10:24:00 DIRECTOR direct SN sim, cache Redis
```

Respostas viram diretivas e aparecem no topo da view do destinatário.

### Diretiva global

Só a persona `DIRECTOR` pode emitir `direct`. Diretivas aparecem na seção `DIRETIVAS` de **todas** as views, no topo, com prioridade máxima.

## Regras de filtro (v0, manuais)

Ordem de prioridade para montar a view de uma sessão `X`:

1. Diretivas ativas do DIRECTOR (sempre)
2. Blockers de X (dependências declaradas ainda não satisfeitas)
3. Dependentes de X (outras sessões esperando X)
4. Recursos que X usa (containers, endpoints mencionados nos logs de X)
5. Eventos recentes de sessões com quem X tem dependência bidirecional
6. Perguntas pendentes envolvendo X
7. Resto (silenciado por padrão)

## Versionamento do protocolo

Este documento é `protocol v0`. Cada view começa com um comentário HTML:

```html
<!-- myco protocol v0 -->
```

Sessões podem checar a versão se quiserem adaptar comportamento.
