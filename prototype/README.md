# myco — Fase 0 (protótipo Python)

Protótipo de validação do protocolo `myco`. **Isso não é o produto final.** O produto final é um daemon em Rust. Este diretório serve apenas para **provar que a teoria funciona** antes de investir em Rust.

## O que tem aqui

- **`mycod.py`** — daemon em Python que escuta `log/*.log`, mantém índice em memória e reescreve `view/*.md` atomicamente
- **`myco-log`** — helper em bash para sessões appendarem eventos manualmente com timestamp correto
- **`myco-hook.py`** — Stop hook do Claude Code que captura blocos `<myco>...</myco>` do output do Claude e appenda como eventos no log automaticamente (sem precisar de tool calls)
- **`test.sh`** — teste end-to-end com 8 cenários, incluindo latência e concorrência
- **`RESULTS.md`** — resultados da validação

## Requisitos

- Python 3.8+
- Um tmpfs montado (`/mnt/ramdisk` por padrão)
- Bash e coreutils GNU (já presentes em qualquer Linux)

## Como rodar o teste

```bash
cd prototype
./test.sh
```

Isso vai:

1. Limpar `/mnt/ramdisk/myco-test/`
2. Subir o daemon
3. Rodar 8 cenários automatizados
4. Imprimir as latências medidas
5. Derrubar o daemon

## Como usar manualmente

Em um terminal, suba o daemon:

```bash
python3 mycod.py /mnt/ramdisk/myco
```

Em outro terminal, escreva eventos:

```bash
export MYCO_SESSION=SN
export MYCO_SWARM=/mnt/ramdisk/myco

./myco-log start webhook.incoming
./myco-log need IAM.auth.v2
./myco-log done webhook.incoming
```

Em um terceiro terminal, leia a view:

```bash
cat /mnt/ramdisk/myco/view/SN.md
```

## Modo automático: hook do Claude Code

Em vez de Claude precisar rodar `myco-log` manualmente via Bash a cada ação, ele só termina o turno com um bloco assim:

```
<myco>
start webhook.incoming
need IAM.auth.v2
</myco>
```

O Stop hook (`myco-hook.py`) é disparado pelo Claude Code quando o turno acaba, lê o transcript JSONL da sessão, encontra o último bloco `<myco>` na resposta do assistant e appenda os eventos no `log/<sessão>.log`. O daemon pega na próxima poll.

Já está registrado em `.claude/settings.json` na raiz do projeto:

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR\"/prototype/myco-hook.py"
      }]
    }]
  }
}
```

Antes de lançar Claude Code:

```bash
export MYCO_SESSION=SN          # nome da sessão (default: basename do cwd)
export MYCO_SWARM=/mnt/ramdisk/myco   # default: /mnt/ramdisk/myco
export MYCO_HOOK_DEBUG=1        # opcional: imprime diagnóstico no stderr
```

Regras do bloco:

- Uma linha = um evento
- Formato `<verbo> <obj> [detail...]`
- Verbos válidos: `start`, `done`, `need`, `block`, `up`, `down`, `direct`, `ask`, `note`
- Linhas em branco e comentários (`# ...`) são ignorados
- Se Claude escrever vários blocos `<myco>` no mesmo turno, **o último ganha** (permite rascunho + revisão)
- Linhas com verbo desconhecido são puladas silenciosamente

Sem bloco no turno → o hook não faz nada (silencioso). Zero overhead.

### Armadilha descoberta: race condition no transcript

Quando o `Stop` hook dispara, o Claude Code **ainda não terminou** de escrever a resposta do assistant no transcript JSONL em disco. Na primeira execução de teste o arquivo tinha 139 bytes (só a `queue-operation` e parte do user prompt) — o texto do assistant aparecia só depois, crescendo até ~1770 bytes.

O `myco-hook.py` contorna isso fazendo polling no transcript por até 500ms, esperando aparecer pelo menos uma linha de `type: assistant` com texto. Se estourar o timeout, o hook sai silencioso em vez de falhar.

Esse é um comportamento observado no Claude Code 2.1.32 em modo `-p`. Em sessão interativa o comportamento pode ser diferente (não testado).

## Por que Python?

- Fase 0 é sobre **validar o protocolo**, não performance absoluta
- Python tem parser de strings, templating e atomicidade de arquivos embutidos
- Iteração rápida durante o design do protocolo
- Todas as conclusões sobre latência, concorrência e correção se mantêm ao portar para Rust (Rust só vai ficar ainda mais rápido)

Ver `RESULTS.md` para os números e a análise completa.

## Limitações (conscientes)

- Polling a 1ms em vez de inotify (decisão de simplicidade)
- Re-render de todas as views a cada evento (otimização óbvia, irrelevante aqui)
- Sem CLI (`status`, `tail`) — só o daemon
- Sem compactação de log
- Sem persistência além do ramdisk

Essas limitações ficam para a Fase 1 em Rust.
