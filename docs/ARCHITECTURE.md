# Arquitetura

Esboço do daemon `myco` em Rust. Propositalmente minimalista.

## Componentes

```
┌─────────────────────────────────────────────────────────┐
│                      myco-daemon                        │
│                                                         │
│  ┌───────────┐   ┌──────────┐   ┌──────────────────┐    │
│  │  watcher  │──▶│  index   │──▶│     renderer     │    │
│  │ (notify)  │   │ (memória)│   │  (template+diff) │    │
│  └───────────┘   └──────────┘   └────────┬─────────┘    │
│        ▲              ▲                   │             │
│        │              │                   ▼             │
└────────┼──────────────┼───────────────────┼─────────────┘
         │              │                   │
    log/*.log      filter rules       view/*.md (atomic)
```

### 1. `watcher`

Usa o crate [`notify`](https://crates.io/crates/notify) para escutar `inotify` recursivamente em `log/`. Para cada mudança (append, criação de arquivo novo), emite um evento interno.

### 2. `index`

Estado em memória do swarm. Estrutura central:

```rust
struct SwarmIndex {
    sessions: HashMap<SessionId, SessionState>,
    events: VecDeque<Event>,           // ring buffer dos últimos N
    resources: HashMap<ResourceId, ResourceState>,
    declarations: Vec<Declaration>,    // needs ativos
    directives: Vec<Directive>,        // diretivas ativas do DIRECTOR
    pending_questions: Vec<Question>,
    last_line_read: HashMap<SessionId, u64>,
}
```

Cada evento novo passa por um parser simples (regex sobre `<ts> <sessao> <verbo> ...`) e atualiza o índice de acordo com o verbo.

### 3. `renderer`

Para cada sessão, aplica as regras de filtro e gera o conteúdo de `view/$X.md` usando templates (`tera` ou `handlebars` ou `format!` direto — vamos pelo mais simples).

Escreve via temp+rename para garantir atomicidade das leituras.

### 4. `filter rules`

V0: código Rust puro, regras hard-coded, descritas em [`PROTOCOL.md#regras-de-filtro-v0-manuais`](PROTOCOL.md#regras-de-filtro-v0-manuais).

V1 (futuro): regras expressas em um arquivo TOML/RON simples, carregado no boot, hot-reload em mudança.

V2 (longe): heurística que ajusta regras baseado em uso real — linhas mostradas mas nunca causadoras de ação viram candidatas a silenciamento.

## Dependências (crates)

Mínimas e maduras:

- `notify` — inotify
- `tokio` — runtime assíncrono (só para watcher + writer)
- `serde` + `toml` — config (se precisar)
- `tempfile` — para escrita atômica
- `chrono` — parsing de timestamps
- `anyhow` + `thiserror` — erros

Nada exótico. Tudo compila offline, binário estático <5MB.

## Ciclo de eventos

```
┌──────────────────────────────────────────────────────┐
│ 1. inotify dispara: log/SN.log cresceu               │
│ 2. watcher lê as linhas novas desde last_line_read   │
│ 3. parser converte cada linha em Event               │
│ 4. index.apply(event) atualiza estado                │
│ 5. renderer identifica quais views foram afetadas    │
│ 6. renderer reescreve view/X.md.tmp                  │
│ 7. rename view/X.md.tmp → view/X.md                  │
│ 8. repete para cada view afetada                     │
└──────────────────────────────────────────────────────┘
```

Latência alvo: **menos de 1ms** entre append no log e view atualizada, no ramdisk.

## Persistência

Zero. O daemon é stateless por design. Se ele morrer, basta reiniciar — ele reconstrói o índice lendo todos os `log/*.log` do início.

Para rotação/compaction, um comando `myco compact` pode ser implementado depois. V0 confia que a execução cabe na sessão de trabalho (horas, não dias).

## CLI

```
myco daemon       # sobe o daemon em foreground
myco daemon -d    # sobe em background
myco status       # imprime visão geral do swarm (lê o índice via socket)
myco tail [SESSAO] # live tail do log agregado
myco view SESSAO  # imprime view/$SESSAO.md (só um cat, mas padronizado)
myco compact      # compacta logs antigos (futuro)
```

## Conexão com as sessões Claude

O daemon **não conversa** com as sessões Claude. A única ponte é o filesystem:

- Sessão escreve em `log/X.log` via Bash tool (`echo >>`)
- Sessão lê `view/X.md` via Read tool

Isso é uma escolha deliberada. Nenhuma sessão precisa saber que o daemon existe. Se o daemon cair, as sessões continuam vendo a última versão das views (ficam estáticas, mas não quebram). Quando o daemon volta, ele reindexa e atualiza.

## Observabilidade

- `myco tail -f` — live tail colorido dos eventos
- `myco status` — tabela do estado atual de cada sessão e recurso
- Logs do próprio daemon em `/tmp/myco-daemon.log`

Sem métricas Prometheus, sem tracing distribuído. É um projeto local.

## Fases de implementação

1. **Fase 0 — validação em shell**: antes de escrever Rust, validar o protocolo com scripts bash + `inotifywait` + `awk`. Quando o protocolo estiver estável, aí Rust.
2. **Fase 1 — daemon monolítico**: tudo junto, uma thread, sem socket, só reescreve arquivos.
3. **Fase 2 — CLI com socket**: `myco status` e `myco tail` via Unix socket local.
4. **Fase 3 — filtro configurável**: regras em TOML com hot-reload.
5. **Fase 4 — aprendizado heurístico**: silenciamento automático de ruído.

Fase 0 é onde começa.
