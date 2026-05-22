# Launch checklist & post draft

*Internal launch artifact for `myco`. Delete or move before final commit if you don't want it in the public repo.*

---

## GitHub repo metadata (apply when ready)

Run this from the local repo (you're authenticated as `cezarfuhr`):

```bash
gh repo edit primoia/myco \
  --description "Coordinate parallel AI agent sessions across providers (Claude, DeepSeek, ...) — text-only protocol + Python daemon" \
  --add-topic claude-code \
  --add-topic ai-agents \
  --add-topic multi-agent-systems \
  --add-topic agent-orchestration \
  --add-topic coordination-protocol \
  --add-topic swarm \
  --add-topic llm-tooling \
  --add-topic python \
  --add-topic developer-tools \
  --add-topic anthropic \
  --add-topic deepseek \
  --add-topic multi-provider
```

Then commit and push the new README + LICENSE:

```bash
git add README.md README.pt-BR.md LICENSE
git commit -m "docs: english README, MIT LICENSE file"
git push
```

After that, GitHub shows: description ✓, topics ✓, license MIT ✓, README in English ✓.

---

## Optional: social preview image

A simple PNG that GitHub uses when the repo is shared on Twitter/LinkedIn/HN.
1280x640px. Background dark, white text, large title `myco`, tagline below.
Upload at Settings → Social preview.

Not strictly required for launch, but ~2x clickthrough when posting to social.

---

## Post draft — "Show HN: myco"

**Title** (rank order):
1. `Show HN: Myco – coordinate Claude + DeepSeek + other LLMs in one agent swarm`
2. `Show HN: I ran a Claude vs DeepSeek code duel through my agent coordination protocol`
3. `Show HN: Myco – text-only coordination protocol for parallel AI coding sessions`

**Body** (~800 words):

---

Hi HN,

I'm a developer who got laid off without warning last September and started a new full-time job in December. In between — and after — I leaned hard on agent CLIs (Claude Code mostly) to build a portfolio of small services in parallel. Partly as a hedge: I didn't want to be caught off-guard again.

The wall I hit was familiar: **one session can't hold a hundred projects in its head**, even with a 1M context window. Late-conversation attention degrades, long contexts blur, and opening 10 tabs of an agent CLI with no coordination is worse than useless — you get conflicts, repeated work, stale assumptions across siblings.

So I built **myco**: a small Python daemon plus a hook protocol that turns N agent sessions into a coordinated swarm. Each session keeps its own clean context but shares an audit log with the others through a silent bus.

Repo: https://github.com/primoia/myco
License: MIT

### How it works

Each session ends every response with a structured block, captured by a Stop hook:

```
<myco>
done login.endpoint ref:origin/feat/login result:ok
ask AUTH which-jwt-lib-are-we-using
</myco>
```

The daemon indexes the event and, on every prompt, a UserPromptSubmit hook injects a personalized markdown view for that session — showing its status, who's blocked on whom, pending questions directed at it, and recent broadcasts.

No tool calls. No central orchestrator. No agent framework. Just markdown + HTTP + hooks.

### The 12 verbs

`start`, `done`, `need`, `block`, `up`, `down`, `ask`, `reply`, `say`, `direct`, `private` (canonical "private note") + `log` / `note` as legacy aliases of `private`, plus key:value tags (`ref:`, `spec:`, `result:`, `addr:`, `re:`).

Each verb has a fixed audience — `say` broadcasts, `private` is private, `ask` is directed and pending, `direct` is a top-priority command from a DIRECTOR session. The daemon lints common mistakes: if you `reply` to someone with no pending ask, it warns; if you `private` something while someone is waiting on you, it warns.

### The fun part — it's multi-provider

Because the protocol is plain text and the launcher uses the Claude Code CLI under the hood, you can point any session at any Anthropic-compatible endpoint. To prove this isn't theoretical, I ran a 3-round experiment between **Claude Opus 4.7** and **DeepSeek v4-pro** through the same myco swarm. The full record (both sessions' independent self-evaluations, the scripts, the rubrics) is at `examples/heterogeneous-swarm/`.

Three rounds, same tenant:

1. **Spec → Impl.** Claude writes `parse_iso8601_duration` spec into `msg/`, DeepSeek implements (7/7 tests in ~1.5min). Claude finds an edge case (`"PT"` empty), DeepSeek fixes (8/8 in ~2min). Clean round-trip, both directions.
2. **LRUCache, both implement independently.** Technical tie: both 9/9 green, both `OrderedDict` + `move_to_end` in ~32 LOC, almost mirrored cross-reviews.
3. **Tetris, both implement, both review.** Both produced 11/11 green tests. Same architecture, similar style. The decider wasn't capability — it was disciplines automated tests don't cover:
   - DeepSeek shipped with bigger canvas, grid lines, score on game-over overlay.
   - Claude shipped with `<div id="overlay" hidden>` defeated by `display: flex` in its own CSS (`[hidden]` from the user-agent stylesheet loses to author rules). Overlay was permanently visible. Logic tests didn't catch it; the CLI session can't open a browser.

Two takeaways that surprised me:

- **Capability converged.** Same `OrderedDict`, same precomputed-rotations idiom, same architectural split. Two models from different vendors handed identical specs produced strikingly similar code. Claude's own self-evaluation notes the suspicion: *"this may reflect similarity of training data more than independent validation."*
- **Discipline at non-tested axes diverged.** Tests pass ≠ feature works. The CLI session is blind to UI. This isn't a model failure — it's a workflow gap that affects whatever model you put behind it.

What this unlocks for swarms in general:
- **Cost mix**: one Opus architect + several cheap DeepSeek/Groq/local implementers
- **Capability mix**: right model per role (design vs bulk code vs review)
- **Resilience**: one provider has an outage, the swarm keeps moving
- **No vendor lock-in**: the protocol doesn't care who's behind any session

### How I actually use it

I work from an ultrawide. ~10 tmux panes across a notebook + 2 LAN VMs. Each pane runs one session with a fixed identity (PRIMOIA, AUTH, FRONT, DIRECTOR, DEEPSEEK-IMPL, ...). I jump between them with Ctrl+PgDn.

My workflow has a hierarchy:
- **Macro session** — I look at all my projects, decide where to dig.
- **Medium session** — fresh session for the chosen project, macro context already in its panel.
- **Micro session** — for a specific routine, I spawn yet another session.

When the macro session asks "what did AUTH end up choosing for JWT?", the answer is already in its panel — AUTH posted `done jwt-lib ref:... result:ok` an hour ago. Nobody had to copy-paste.

I'm the router. The daemon is the bulletin board. The sessions stay sharp.

### What's done

- v1.1 protocol (12 verbs + key:value + rich messages in `msg/`)
- Python daemon, in-memory state, file-backed tenants
- HTTP API with bearer auth, multi-tenant isolation
- Cross-VM tested (daemon on one machine, sessions on others)
- 285 unit tests passing
- Auto-lint of common mistakes
- Heterogeneous swarm validated (Claude + DeepSeek, see `examples/`)
- `--resume` integration with session IDs — sessions survive across days

### What's missing

- Browser UI for the daemon (today the only "view" is the per-session panel injected into prompts)
- Adapters for non-Claude-Code clients (the wire protocol is generic; the hook contract today is Claude Code specific — adapting to Aider, Codex, Continue, etc. is glue)
- More examples beyond the spec-impl and the duel
- Probably edge cases I haven't hit

### Why I'm posting this now

It's been public on GitHub for a month with 0 stars and no description, because I wasn't sure if anyone besides me would care. I've decided to find out.

If you operate multiple coding sessions across providers and feel the same friction, I'd love feedback. If this overlaps with something existing I missed, please point me there. If the protocol verbs feel wrong, that's the most useful kind of bug to hear about now.

— Cezar

---

## Distribution checklist

After posting on HN, copy/adapt to:
- [ ] Reddit /r/LocalLLaMA — title: `myco: coordination protocol for parallel Claude Code sessions [OSS]`
- [ ] Reddit /r/programming — same
- [ ] X/Twitter thread — 5-7 tweets, opening with the macro/medium/micro hierarchy story
- [ ] Anthropic Discord #showcase channel
- [ ] dev.to long-form version
- [ ] Personal LinkedIn if you want career signal

Don't do all on day 1. HN + Reddit + Discord on day 1, Twitter on day 2, dev.to/LinkedIn on day 3-4 if there's traction.

## What "success" looks like

Honest baseline (your strategy doesn't depend on traction):
- 0-50 stars in week 1: small audience exists, niche real but tiny. No loss.
- 100-500 stars: solid niche win. Issues + PRs incoming. Career signal locked in.
- 1k+ stars: you're now "the author of myco". Optional commercial paths open up.

In all cases the CLT continues. In all cases the technique remains yours. The only downside is one evening of work.

Good luck.
