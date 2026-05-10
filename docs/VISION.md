# Visão do myco

> Documento de tese arquitetural. Complementa [CONCEPT.md](CONCEPT.md) (o *como* técnico) e [PROTOCOL.md](PROTOCOL.md) (o *quê* operacional). Aqui mora o **porquê** e o **para onde**.

---

## 1. O problema que justifica myco existir

Coordenação entre sessões de AI hoje se resolve por dois caminhos, ambos com custos que pioram com escala:

**Subagentes (hub-and-spoke)**
- Um Claude "pai" delega a filhos efêmeros, integra os retornos, decide.
- O pai acumula contexto linearmente com cada delegação: prompt + N delegações + N sumários + raciocínio próprio.
- A execução "limpa" nunca existe — o pai está sempre lá, carregando tudo.
- Observação contínua não é possível: filhos são chamados sob demanda, não vigiam.

**MCP servers (tool federation)**
- Cada server injeta N tools no schema do modelo.
- O modelo pondera **todas** as tools a cada decisão. Custo cresce em O(tools_totais).
- 3 VMs × 10 tools = 30 tools para escolher toda vez. Tempo-até-primeiro-token sofre.
- Deferred tools / ToolSearch mitigam mas adicionam latência própria.

Ambos colapsam quando a frota (de sessões, de VMs, de humanos) passa de poucos agentes acoplados para muitos agentes soltos colaborando em prazos longos.

---

## 2. A tese central

> **Trocar hierarquia cognitiva por espaço observável compartilhado.**

- Sessões são **soberanas**, não subordinadas. Cada uma é dona do seu contexto, suas ferramentas locais, seu histórico.
- Artefatos (`msg/*.md`, `log/*.log`, referências git) são **imutáveis** e **auditáveis**. São a interface entre sessões, não chamadas diretas.
- O **view** injetado no início de cada prompt é o substrato comum — curado por sessão, mas derivado de um estado global legível por todos.
- Coordenação vive em **texto estruturado**, não em tool-schema. Custo por sessão é **constante**, não cresce com o tamanho do swarm.

Em uma frase: **myco é espaço compartilhado com curadoria, não orquestração centralizada.**

---

## 3. Propriedades que emergem da tese

Essas não são features adicionadas — são consequências naturais de escolher a topologia peer-observável.

### 3.1 Pipeline com higiene de contexto por construção
Sessão `RESEARCHER` pesquisa, produz `msg/SPEC-001.md`, faz `done`, fica idle. Sessão `EXECUTOR` inicia fresca, lê **só o artefato**, executa com budget de contexto cheio. O scratch work da pesquisa nunca contamina a execução. Subagente não consegue isso porque o pai sempre sobrevive à delegação.

### 3.2 Guardian / sidecar read-only
Sessão `SECURITY` ou `POLICY` com acesso só-leitura ao painel, rodando em paralelo, sem bloquear ninguém. Quando detecta violação, injeta via `say` ou `ask`. Humano aprova a regra uma vez; guardian aplica N vezes. É **kernel + userspace**: workers no userspace, guardian fiscalizando via view. Subagente não oferece observação contínua.

### 3.3 Ground truth substitui alucinação
Worker não chuta o schema do DB — `DBA` publicou `msg/DB-SCHEMA-003.md`. Worker não adivinha o contrato da API — `BACK` publicou `msg/API-012.md`. O view vira **fonte autoritativa local**, reduzindo alucinação sem RAG, sem tool-call extra.

### 3.4 Heterogeneidade de modelo sem fricção
Sessões de grunt work (parse, formatação, scraping) em Haiku. Sessões de arquitetura em Opus. O contrato entre elas é `msg/`, não chamada direta — então mixar modelos não exige glue code, só convenção de artefato.

### 3.5 Compressão de contexto via artefato, não conversa
Projeto longo: histórico de conversa vira lastro. Em myco, o "estado do mundo" vive nos `msg/` e no view. Nova sessão começa lendo artefatos, não replay de conversa. É **event sourcing aplicado à colaboração cognitiva**.

### 3.6 Replay determinístico
Log de `<myco>` blocks é máquina de estados reproduzível. Dá para reencenar a história de um swarm, auditar decisões, debugar coordenação. Subagente não deixa trilha estruturada — só sumários voláteis.

### 3.7 Blast radius contido
Sessão destrutiva (migration, refactor arriscado) vive na VM dela. Guardian observa; `say stop` se necessário. Estrago não cruza fronteira de sessão. Em subagente, pai e filho compartilham destino.

### 3.8 Colaboração async entre humanos e timezones
Dev A drop `msg/SPEC-001.md` às 23h, dorme. Executor pega, produz `done ref:branch`. Dev B acorda em outro fuso, revisa artefato (não conversa). O swarm opera **sem todos os humanos presentes**.

### 3.9 Especialização por ambiente, não por prompt
Claude numa VM com só `psql` e docs de SQL vira "DBA" sem system prompt engenhoso. O ambiente molda a personalidade. Barato e robusto.

### 3.10 Escala favorável conforme a frota cresce
Custo de coordenação myco cresce com o tamanho do painel (controlável por curadoria). Custo MCP cresce com o número de tools (não controlável sem tirar capacidade). Cruzamento provável acima de ~2–3 VMs / dezenas de tools.

---

## 4. Cenários onde myco ganha

### 4.1 Squads multi-dev remoto (caso mais forte)
Front e back em repos separados, contrato de API como `msg/` congelado, `done ref:origin/feat/x` como supply chain. Coordenação embutida no contexto do Claude de cada dev — sem abrir Slack, sem standup. **Único aspecto que Slack/GitHub/Linear não cobrem: o Claude do outro dev já sabe o que o seu acabou de publicar.**

### 4.2 Single-human, N VMs Linux (server / db / front)
Cada Claude soberano na sua VM, com tools locais (psql, journalctl, dev server). MCP sofre com tool selection overhead quando a frota cresce. myco paga custo constante por sessão. Para ops longas e debug distribuído, vence.

### 4.3 Pipelines research → execute
Handoff limpo via `msg/`. Executor começa com contexto zerado, só a spec congelada. Trabalho cognitivo do pesquisador não entra no budget do executor.

### 4.4 Ops longas com guardian observando
Dias de trabalho, risco real, necessidade de auditoria e intervenção policy-driven sem bloquear workers.

---

## 5. Onde myco NÃO ganha (ser honesto importa)

- **Single-session single-repo** com tarefa curta. Overhead > benefício.
- **Spec emerge durante execução.** Se o executor precisa voltar ao pesquisador várias vezes, o ciclo rebound come o ganho de contexto limpo. Funciona melhor quando o spec **congela de verdade**.
- **Frotas muito pequenas** (< 2 sessões). Resolver com subagente ou conversa direta é mais simples.
- **Acoplamento forte** — mesmo arquivo, mesma feature, mesma função. Coordenar via myco vira burocracia; mais simples uma sessão só.
- **Conhecimento tácito** que não cabe em markdown. Intuição de código, feeling de arquitetura — isso não transfere via `msg/`.

---

## 6. Limitações atuais (honestidade sobre o estado)

- **`<myco>` block depende de indução.** Se o Claude esquece de escrever, a coordenação falha silenciosamente. Frágil até virar enforcement.
- **CLAUDE.md como contrato é hack comportamental**, não invariante formal.
- **Multi-channel sozinho é namespacing**, não diferencial. Vira ponto real só com semântica cross-channel.
- **Não há validação de contrato** — `need X` e `done X` se encontram por convenção de nome, não por schema.
- **Staleness**: publicações podem ficar desatualizadas sem mecanismo explícito de `supersede` / `retract`.
- **DIRECTOR é mais teatro que arquitetura** — hoje o humano é o coordenador real; o protocolo precisa dar ao DIRECTOR capacidade concreta de mediação.

---

## 7. Para onde vamos

Roadmap derivado da tese, não de features avulsas.

### Enforcement substitui indução
Bloco `<myco>` vira DSL validada (schema, parser estrito, erros visíveis). Esquecer de escrever deixa de ser silencioso. Caminho possível: hook valida formato e avisa o modelo quando falta.

### Semântica cross-channel
Canais param de ser silos:
- Referência cruzada de `msg/` (canal `arch` publica spec; canal `impl` consome).
- Broadcast seletivo (enviar `say` para lista de canais).
- DIRECTOR multi-canal com painel agregado (grafo de deps entre squads).

### Validação de contrato
`need X spec:msg/REQ-001.md` declara expectativa. `done X spec:msg/DELIV-001.md` declara entrega. Daemon compara, sinaliza mismatch. Sem isso, contrato é só nome compartilhado.

### Verbos de staleness
`supersede msg/API-012.md by msg/API-013.md` — publicações velhas são marcadas; painel esconde ou destaca. `retract` para erros graves.

### Painel enriquecido do DIRECTOR
Grafo de dependências em forma humana. Conflitos destacados (duas sessões editando mesmo recurso, `need` sem `done` correspondente, `block` circular). DIRECTOR vira posto de observação com poder real.

### Benchmark vs alternativas
Medir em cenário multi-VM: tempo-até-primeiro-token, tokens gastos, taxa de erro de coordenação. myco vs subagente vs MCP. Sem números, o pitch é literatura.

---

## 8. Abstract de uma linha

> myco é um protocolo de coordenação entre sessões Claude que substitui hierarquia cognitiva por espaço observável compartilhado — trocando integração custosa no orquestrador por artefatos imutáveis auditáveis, com escala favorável conforme a frota cresce e propriedades emergentes (higiene de contexto, guardian RO, ground truth, replay determinístico) que subagentes e MCP não oferecem.

---

## 9. Notas para o próximo Claude lendo este documento

Se você é uma sessão iniciando trabalho em myco:

- A tese em §2 é o norte. Features que não derivam dela pedem justificativa extra.
- Antes de adicionar verbo novo, pergunte: isso segue da tese ou é feature avulsa?
- Quando algo parecer duplicar MCP ou subagente, releia §1 e §3 — o custo estrutural é diferente.
- A seção §5 existe para te impedir de empurrar myco onde não cabe. Respeite.
- Se o usuário propuser algo que contradiz a tese, não ceda por polidez. Diga.
