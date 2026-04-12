# Conceito

## O problema real

Quando múltiplas sessões Claude trabalham em projetos interdependentes, o humano vira gargalo. Ele fica traduzindo "o Claude A precisa que o Claude B faça X antes de continuar", manualmente, uma mensagem por vez. MCP existe mas adiciona latência (JSON-RPC, ~50-200ms por leitura), overhead de processo e não resolve o problema de consciência compartilhada entre as sessões.

## A descoberta central

O filesystem num ramdisk Linux **já é** um broker de mensagens distribuído:

- `mv` entre diretórios no mesmo FS é **atômico** — primitiva de consenso grátis
- Escritas `O_APPEND` menores que 4KB são atômicas entre processos — pub/sub lock-free
- `inotify` dá notificação reativa sub-milissegundo
- Page cache compartilhado entre processos = múltiplos leitores sem duplicação
- Ramdisk (tmpfs) elimina todo IO de disco

Qualquer coisa que o `myco` adicione em cima disso precisa justificar o custo. O daemon Rust **não reimplementa** coreutils — ele adiciona o único valor que falta: **curadoria personalizada por sessão**.

## A metáfora: campo que amadurece

Esqueça "pipeline" (s1 → s2 → s3). Pense num campo onde cada tarefa é uma **declaração**:

> "Preciso que estas condições sejam verdade. Quando eu terminar, estas novas condições passam a valer."

As sessões andam pelo campo, filtram o que está maduro (precondições satisfeitas) e compatível com seu papel, colhem atomicamente, trabalham, plantam os frutos. O pipeline **emerge** do campo. Não precisa de scheduler. Não precisa de "espere s1 terminar". O fato de s1 ter publicado o efeito é, por si só, o gatilho que amadurece a declaração do s2.

## Três primitivas, nada mais

1. **Log append-only por sessão** (`log/$SESSAO.log`)
   Cada Claude escreve apenas no seu próprio arquivo. Zero contenção, zero lock. Uma linha por evento: `timestamp sessao verbo objeto`.

2. **View curada por sessão** (`view/$SESSAO.md`)
   Arquivo markdown reescrito pelo daemon sempre que o estado global muda. Cada sessão tem uma view diferente, porque cada uma tem preocupações diferentes. Topo = resumo acionável. Fundo = detalhes pagináveis (Claude lê mais se precisar).

3. **CLAUDE.md compartilhado**
   Induz toda sessão a ler `view/$EU.md` antes de qualquer ação e a escrever em `log/$EU.log` depois. Duas operações. Nada mais.

## Por que views personalizadas

Se cada sessão lesse o log cru das outras, perderia contexto em ruído irrelevante. A view filtra:

- **Dependências que te afetam** — se você declarou precisar de `IAM.auth.v2`, eventos de IAM viram prioridade máxima pra você
- **Blockers seus** — o que está impedindo seu trabalho agora
- **Dependentes seus** — quem está esperando você
- **Estado atual de recursos compartilhados** — containers, endpoints, schemas
- **Eventos recentes relevantes** — não tudo, só o que casa com seu papel

O daemon aprende com o tempo: linhas que aparecem na view mas nunca causam ação daquela sessão viram candidatas a serem silenciadas em versões futuras das regras de filtro.

## Consciência, não mensageria

A pergunta certa não é "como A manda mensagem pra B". É "como B **sabe** o que A está fazendo quando B decidir perguntar". A resposta é: uma leitura única de `view/B.md` deve conter a foto completa do swarm do ponto de vista de B. Pull, não push. Consciência sob demanda.

## A persona DIRECTOR (humano + sessão conselheira)

O humano (você) e a sessão Claude que conversa com ele (como esta conversa aqui) formam juntos uma persona chamada `DIRECTOR`. Essa persona:

- **Escreve diretivas** em `log/DIRECTOR.log` — decisões de arquitetura, prioridades, redirecionamentos
- **Lê `view/DIRECTOR.md`** — consolidado de tudo, com perguntas pendentes dos workers

Eventos de `DIRECTOR` têm prioridade máxima no filtro: aparecem no topo de todas as views como "Diretivas". Nenhum worker ignora.

Isso cria simetria total: humano e agentes usam o mesmo protocolo. O humano é só mais um nó, com uma autoridade diferente, mas com a mesma mecânica de log+view.

## Leitura parcial e o "enganar o Claude"

O `Read` do Claude aceita `offset` e `limit`. As views são estruturadas com o mais importante no topo:

```markdown
# AGORA (sempre leia primeiro)
...

# SEUS BLOQUEADORES
...

# EVENTOS RELEVANTES (30s)
...

# DETALHES (offset/limit conforme necessário)
...
```

Claude lê as primeiras ~50 linhas e 90% das vezes já sabe o que fazer. Quando precisa de mais contexto, pagina. O daemon pode até deixar marcadores explícitos tipo `# Para detalhes de IAM.auth.v2, leia linhas 200-250`.

Não é FUSE. Não é truque de syscall. É markdown normal, gerado em tempo real, mas sempre estático no momento da leitura. O daemon garante que o arquivo está fresco via escrita atômica (`rename()` de um tempfile).

## Princípios de design

1. **O filesystem é a fonte da verdade.** O daemon é um índice em memória + renderer. Se ele morrer, nada é perdido — basta reler os logs.
2. **Uma leitura = consciência máxima.** Amortize tool calls do Claude.
3. **Escritores únicos.** Cada arquivo tem exatamente um escritor. Zero contenção por design.
4. **Markdown puro.** Sem YAML, sem JSON, sem Protobuf. O formato nativo do Claude é o formato nativo do swarm.
5. **Metadata no nome do arquivo.** `ls` e `grep` são query engines grátis.
6. **Inotify, não polling.** Reação imediata, zero CPU idle.
7. **Filtro começa burro.** Regras manuais primeiro. Heurística aprendida só depois de ver uso real.

## O que fica de fora (por enquanto)

- Autenticação/autorização entre sessões (todas confiam umas nas outras, rodam na mesma máquina)
- Rede (é um protocolo local a um host)
- UI web (TUI e `cat view/*.md` bastam)
- Persistência além do ramdisk (export manual pra disco quando necessário)
- ML de verdade no filtro (heurística estatística simples chega longe)

## O que é sucesso

- Rodar 3+ sessões Claude em projetos interdependentes sem humano intervindo por horas
- Latência de log → view atualizada em menos de 1ms
- Cada sessão precisa de ≤ 2 tool calls pra ter consciência plena do swarm
- View de cada sessão cabe em menos de 2000 tokens
- Daemon consome menos de 20MB de RAM e roda como binário único sem dependências externas
