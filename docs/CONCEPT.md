# Conceito

## O problema real

Quando múltiplas sessões Claude trabalham em projetos interdependentes, o humano vira gargalo. Ele fica traduzindo "o Claude A precisa que o Claude B faça X antes de continuar", manualmente, uma mensagem por vez. MCP existe mas adiciona latência (JSON-RPC, ~50-200ms por leitura), overhead de processo e não resolve o problema de consciência compartilhada entre as sessões.

## A descoberta central

O filesystem num ramdisk Linux **já é** um broker de mensagens distribuído:

- `mv` entre diretórios no mesmo FS é **atômico** — primitiva de consenso grátis
- Escritas `O_APPEND` menores que 4KB são atômicas entre processos — pub/sub lock-free
- Page cache compartilhado entre processos = múltiplos leitores sem duplicação
- Ramdisk (tmpfs) elimina todo IO de disco

Qualquer coisa que o `myco` adicione em cima disso precisa justificar o custo. O daemon **não reimplementa** coreutils — ele adiciona o único valor que falta: **curadoria personalizada por sessão**.

## A metáfora: campo que amadurece

Esqueça "pipeline" (s1 → s2 → s3). Pense num campo onde cada tarefa é uma **declaração**:

> "Preciso que estas condições sejam verdade. Quando eu terminar, estas novas condições passam a valer."

As sessões andam pelo campo, filtram o que está maduro (precondições satisfeitas) e compatível com seu papel, colhem atomicamente, trabalham, plantam os frutos. O pipeline **emerge** do campo. Não precisa de scheduler. Não precisa de "espere s1 terminar". O fato de s1 ter publicado o efeito é, por si só, o gatilho que amadurece a declaração do s2.

## Três primitivas, nada mais

1. **Log append-only por sessão** (`log/$SESSAO.log`)
   Cada sessão escreve apenas no seu próprio arquivo (via daemon HTTP ou filesystem fallback). Zero contenção, zero lock. Uma linha por evento: `timestamp sessao verbo objeto`.

2. **View curada por sessão** (`view/$SESSAO.md`)
   Arquivo markdown reescrito pelo daemon sempre que o estado global muda. Cada sessão tem uma view diferente, porque cada uma tem preocupações diferentes. Topo = resumo acionável. Fundo = detalhes pagináveis.

3. **CLAUDE.md cooperativo + injeção mecânica**
   O `CLAUDE.md` estabelece legitimidade ("você faz parte de um swarm, confie no contexto injetado") e o hook `UserPromptSubmit` garante entrega mecânica da view a cada prompt. Nenhum dos dois sozinho é suficiente — a combinação foi validada experimentalmente (ver [`prototype/EXPERIMENT.md`](../prototype/EXPERIMENT.md)).

## Por que views personalizadas

Se cada sessão lesse o log cru das outras, perderia contexto em ruído irrelevante. A view filtra:

- **Dependências que te afetam** — se você declarou precisar de `IAM.auth.v2`, eventos de IAM viram prioridade máxima pra você
- **Blockers seus** — o que está impedindo seu trabalho agora
- **Dependentes seus** — quem está esperando você
- **Estado atual de recursos compartilhados** — containers, endpoints, schemas
- **Eventos recentes relevantes** — não tudo, só o que casa com seu papel
- **Broadcasts** — avisos gerais de qualquer sessão
- **Peers** — quem mais está no swarm e há quanto tempo foi visto

O daemon aprende com o tempo: linhas que aparecem na view mas nunca causam ação daquela sessão viram candidatas a serem silenciadas em versões futuras das regras de filtro.

## Consciência, não mensageria

A pergunta certa não é "como A manda mensagem pra B". É "como B **sabe** o que A está fazendo quando B decidir perguntar". A resposta é: a view injetada automaticamente via hook contém a foto completa do swarm do ponto de vista de B. Pull, não push. Consciência sob demanda.

## A persona DIRECTOR (humano + sessão conselheira)

O humano e a sessão Claude que conversa com ele formam juntos uma persona chamada `DIRECTOR`. Essa persona:

- **Escreve diretivas** em `log/DIRECTOR.log` — decisões de arquitetura, prioridades, redirecionamentos
- **Lê `view/DIRECTOR.md`** — consolidado de tudo, com tabela de sessões, grafo de dependências e conflitos detectados

Eventos de `DIRECTOR` têm prioridade máxima no filtro: aparecem no topo de todas as views como "Diretivas". Nenhum worker ignora.

Isso cria simetria total: humano e agentes usam o mesmo protocolo. O humano é só mais um nó, com uma autoridade diferente, mas com a mesma mecânica de log+view.

## Princípios de design

1. **O filesystem é a fonte da verdade.** O daemon é um índice em memória + renderer. Se ele morrer, nada é perdido — basta reler os logs.
2. **Uma injeção = consciência máxima.** Zero tool calls. View chega automaticamente via hook.
3. **Escritores únicos.** Cada arquivo tem exatamente um escritor. Zero contenção por design.
4. **Markdown puro.** Sem YAML, sem JSON, sem Protobuf. O formato nativo do Claude é o formato nativo do swarm.
5. **Metadata no nome do arquivo.** `ls` e `grep` são query engines grátis.
6. **Polling ultrarrápido.** 1ms de intervalo em ramdisk — custo desprezível, implementação trivial.
7. **Filtro começa burro.** All-see-all primeiro. Filtro inteligente depois de ver uso real.

## O que já funciona (v1.1)

- Transporte HTTP cross-VM com Bearer token auth
- Mensagens ricas via `msg/` (imutáveis, sanitizadas, auto-ack)
- Broadcast (`say`), perguntas dirigidas (`ask`/`reply`), diretivas (`direct`)
- Last-seen timestamps e seção PEERS nas views
- Question TTL (30min) para evitar acúmulo de perguntas stale
- View do DIRECTOR com grafo de dependências e detecção de conflitos
- Launcher `myco` para setup zero de sessões
- 195 testes automatizados

## O que fica de fora (por enquanto)

- UI web (terminal + view markdown bastam)
- Persistência além do filesystem (export manual quando necessário)
- ML de verdade no filtro (heurística estatística simples chega longe)
- Namespace protection per-session (tokens por sessão vs token compartilhado)
- Validação de `ref:` no `done` (daemon aceita qualquer string)

## O que é sucesso

- Rodar 3+ sessões Claude em projetos interdependentes sem humano intervindo por horas
- Latência de log → view atualizada em menos de 3ms
- Cada sessão precisa de **zero** tool calls pra ter consciência plena do swarm (injeção automática)
- View de cada sessão cabe em menos de 2000 tokens
- Daemon consome menos de 5MB de RAM
