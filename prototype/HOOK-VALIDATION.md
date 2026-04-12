# Validação do hook do Claude Code — resultados

**Data**: 2026-04-11
**Ambiente**: Linux, tmpfs em `/mnt/ramdisk`, Python 3 (CPython), Claude Code 2.1.32
**Artefatos**: `prototype/myco-hook.py`, `.claude/settings.json`

## Objetivo

Provar que o Claude Code pode alimentar o protocolo `myco` **sem** precisar chamar `myco-log` explicitamente via tool calls. A ideia é instrumentar o Claude com um `Stop` hook que lê o transcript JSONL ao fim de cada turn, extrai um bloco `<myco>...</myco>` do texto do assistant, e appenda os eventos no `log/<sessão>.log` do swarm.

O daemon `mycod.py` (validado na Fase 0, ver `RESULTS.md`) pega o resto como já fazia antes.

## Arquitetura

```
┌────────────────────┐       ┌────────────────────┐       ┌───────────────┐
│  Claude Code (-p)  │──────▶│  myco-hook.py      │──────▶│  log/S.log    │
│  produz resposta   │ Stop  │  (hook, Python)    │ append│  (append-only)│
│  com <myco> block  │ hook  │                    │       └───────┬───────┘
└────────────────────┘       └────────────────────┘               │
                                      ▲                           │ poll 1ms
                                      │ JSONL                     ▼
                                      │                   ┌───────────────┐
                             ~/.claude/projects/...jsonl  │  mycod.py     │
                                                          │  (daemon)     │
                                                          └───────┬───────┘
                                                                  │ atomic rename
                                                                  ▼
                                                          ┌───────────────┐
                                                          │  view/S.md    │
                                                          └───────────────┘
```

## O que foi testado e passou

### Bateria isolada (transcript fake, sem Claude real)

| # | Cenário | Resultado |
|---|---|---|
| 1 | Bloco simples com 2 eventos | ok, 2 eventos appendados, view atualizada |
| 2 | Múltiplos blocos `<myco>` no mesmo turn | ok, **último** bloco ganha (rascunho descartado) |
| 3 | Turn sem bloco | ok, hook sai silencioso, nada criado |
| 4 | Verbo inválido misturado com válidos | ok, verbo inválido ignorado, válidos passam |
| 5 | Comentários (`#`) e linhas em branco | ok, ignorados |
| 6 | Turn com `tool_use` intermediário (text → tool_use → text final) | ok, texto final é coletado |
| 7 | Bloco de `thinking` na mesma mensagem | ok, ignorado (só `text` é considerado) |

### Teste end-to-end com Claude Code real

Comando:

```bash
cd /home/cezar/Workspace/myco
MYCO_SWARM=/mnt/ramdisk/myco-final MYCO_SESSION=SM MYCO_HOOK_DEBUG=1 \
  claude -p --permission-mode bypassPermissions --tools "" --model sonnet \
         --debug-file /tmp/final-debug.log < /tmp/myco-prompt.txt
```

Prompt pedia pra Claude anunciar o início de `payment.flow` precisando de `SN.webhook.incoming` e terminar com um bloco `<myco>` contendo `start payment.flow` e `need SN.webhook.incoming`.

**Sequência observada:**

1. Claude Code carregou `.claude/settings.json` do projeto
2. Matcher do `Stop` hook encontrado (debug log: `Found 1 hook matchers in settings`)
3. Claude produziu a resposta correta com o bloco `<myco>` no final
4. Stop hook disparou
5. `myco-hook.py` extraiu 118 chars de texto do assistant (após polling)
6. 2 eventos parseados e appendados em `log/SM.log`:
   ```
   2026-04-11T22:18:27 SM start payment.flow
   2026-04-11T22:18:27 SM need SN.webhook.incoming
   ```
7. Daemon `mycod.py` detectou o delta no próximo poll (~1ms)
8. `view/SM.md` re-renderizada com:
   - `Status: **active** — start payment.flow`
   - `Bloqueado por: SN.webhook.incoming`
   - Seção "SEUS BLOQUEADORES" populada
   - Eventos relevantes listados no bloco de código

Resultado: **primeira validação ponta-a-ponta real do protocolo `myco` com uma sessão Claude Code de verdade**. Os 8 testes da Fase 0 (RESULTS.md) eram bash simulando Claude; esse é Claude Code 2.1.32 executando de verdade.

## Armadilha descoberta (não está na documentação)

### Race condition no Stop hook

Durante o primeiro teste real, o hook disparou mas reportou `no assistant text found for this turn`. Inspeção via `--debug-file`:

```
[myco-hook] transcript_path: '.../740ec477-dee2-4b7f-9814-9d96586233b4.jsonl'
[myco-hook] transcript size: 139 bytes
[myco-hook] text extracted: 0 chars
```

Depois que o hook terminou e o processo claude encerrou, o arquivo tinha **1770 bytes** — com o assistant message completo. Conclusão: o Claude Code chama o Stop hook **antes** de persistir a mensagem final do assistant no transcript JSONL em disco.

### Correção aplicada

`myco-hook.py` faz polling no transcript: intervalo de 20ms, timeout de 500ms, procurando por uma linha `type: assistant` com conteúdo `text`. Se aparecer, extrai e segue; se estourar o timeout, sai silencioso sem falhar.

Na re-execução, o arquivo já estava com 1770 bytes na primeira leitura — a janela de race é bem estreita (dezenas de ms), o poll quase nunca precisa esperar, mas o fallback existe caso esteja sob carga.

### Gravidade

- **Só observada em `-p` mode** (não testado em sessão interativa)
- **Não documentada** pela equipe do Claude Code (conforme `claude-code-guide` subagent)
- **Latência acrescida**: zero no caso comum, até 500ms no pior caso
- **Falha modo**: silencioso, eventos perdidos para aquele turn (aceitável pra Fase 0)

## Outros achados relevantes

### Payload do Stop hook

Contrário ao que a documentação inicial sugeriu, o payload recebido via stdin contém apenas:

```json
{
  "session_id": "...",
  "transcript_path": "/abs/path/to/session.jsonl",
  "cwd": "/current/working/dir",
  "permission_mode": "bypassPermissions",
  "hook_event_name": "Stop",
  "stop_hook_active": false
}
```

**Não há** campo `last_assistant_message`. A única fonte de verdade para o texto do turn é o transcript JSONL. Isso reforça a importância do polling.

### Flags que funcionam juntos

- `--permission-mode bypassPermissions` não exige aprovação interativa de hooks
- `--tools ""` desabilita tools mas **não** afeta dispatch de hooks
- `.claude/settings.json` do projeto é carregado por default em `-p` mode
- `--debug-file /tmp/x.log` é a única forma prática de observar hook dispatch em `-p`

### Estrutura do transcript JSONL

Cada linha é um JSON object com:
- `type`: `user`, `assistant`, ou `queue-operation`
- `message.content`: string (para user prompts simples) ou lista de blocos `{type: text|thinking|tool_use|tool_result, ...}`
- O hook só considera blocos `type: text` de mensagens `type: assistant`

## O que a validação confirma

1. **O modelo "tag block no output → log → view" funciona com Claude Code real.** Zero tool calls adicionais, zero overhead pro loop de raciocínio do Claude.

2. **Settings do projeto propagam pro subprocess `claude -p`.** Nenhuma configuração extra é necessária além de commitar `.claude/settings.json`.

3. **O protocolo `myco` pode ser adotado incrementalmente.** Um Claude pode escrever blocos `<myco>` no final do turn quando faz sentido e ignorar nas demais vezes — o hook só faz algo quando acha o bloco.

4. **A race condition do Stop hook é contornável sem mudança de arquitetura.** Polling com timeout é suficiente para a Fase 0.

## Limitações conhecidas (não testadas)

- **Sessão interativa (TUI, não `-p`).** Timing do Stop hook pode ser diferente, polling pode não ser suficiente, ou pode ser mais rápido. Não testado.
- **Múltiplos Claudes concorrentes na mesma swarm.** A arquitetura de um-escritor-por-arquivo deve garantir zero contenção (cada sessão = seu próprio log), mas não foi estressado.
- **Múltiplos turns na mesma sessão.** Só testei 1 turn. Em sessão longa o hook dispararia N vezes, e cada disparo precisa capturar **apenas** o turn mais recente (o código faz isso, walking backwards until `type: user`, mas o comportamento não foi validado com N > 1).
- **Transcripts muito grandes.** O polling lê o JSONL inteiro a cada tentativa. Com MB de transcript, o custo cresce linearmente. Aceitável pra sessões de horas, não pra dias.
- **Sessão Claude interrompida (Ctrl+C).** Stop hook não dispara em interrupções, então eventos do último turn incompleto são perdidos. Documentado pela doc oficial.
- **`stop_hook_active: true`.** O payload traz essa flag quando o hook já bloqueou antes. O hook atual não usa — irrelevante porque nunca bloqueia. Se evoluirmos pra bloquear (por exemplo, rejeitar blocos malformados e pedir Claude pra corrigir), precisa respeitar essa flag pra não entrar em loop.

## Comparação com a alternativa: `Bash(./myco-log ...)`

| Aspecto | Tool call explícito | Hook + tag block |
|---|---|---|
| Turns por evento | 1-2 (Claude decide a call, roda tool, espera resultado) | 0 (só texto) |
| Overhead pra Claude | ~200-500ms por tool call | ~0ms (só output) |
| Fidelidade à narrativa | Quebrada (precisa parar pra "executar") | Contínua (é só prosa + bloco no fim) |
| Falha segura | Erro vira mensagem do tool, Claude vê | Silencioso, eventos perdidos |
| Auditoria | Cada tool call no transcript | Só bloco no texto do assistant |
| Rastreabilidade pós-facto | Alta (tool_use + tool_result estruturados) | Baixa (precisa regex no texto) |

**Veredito da Fase 0:** hook + tag block é o caminho certo pro fluxo principal. Tool call explícito pode coexistir como alternativa pra casos raros onde falha segura não é aceitável (ex: evento crítico onde eu preciso saber se chegou).

## Conclusão

A segunda validação (hook com Claude Code real) **passou** no caminho feliz e revelou uma armadilha de timing que foi corrigida sem mudança de design. O protocolo `myco` pode ser alimentado automaticamente por sessões Claude Code sem burden de tool calls explícitas — bastando o Claude incluir um bloco `<myco>` no fim do turn quando quiser publicar estado.

Combinado com a Fase 0 (`RESULTS.md`), a viabilidade técnica do conceito está provada ponta-a-ponta:

1. Claude escreve markdown normal com bloco `<myco>` no fim
2. Hook extrai o bloco, appenda no log do swarm
3. Daemon atualiza as views das sessões em ~1ms
4. Próxima sessão a ler uma view vê o estado atualizado

O que **ainda está em aberto** é se a estrutura das views (seções, filtros, formato) vai ser útil na prática para Claude — isso só se valida usando o sistema em uma tarefa real, não em testes sintéticos. Esse é o próximo passo natural.
