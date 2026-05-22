# How to record the demo GIF/cast for the README

The README's first impression would benefit hugely from a 15–30s animated demo at the top, showing the daemon coming up and two sessions exchanging an `ask`/`reply` through the bus. The text guides a reader; the GIF *proves it works*.

I (the assistant) can't generate GIFs/videos — this needs to be recorded on your machine. Two tool options, in order of recommendation:

## Option 1 — `vhs` by Charm (recommended)

VHS records terminal sessions from a **declarative script**, so the result is reproducible, edits cleanly, and the timing isn't tied to your typing speed. Best for a polished README hero.

### Install vhs

```bash
# macOS
brew install vhs ttyd ffmpeg

# Linux (Debian/Ubuntu)
# Get the .deb from https://github.com/charmbracelet/vhs/releases
# or use Go: go install github.com/charmbracelet/vhs@latest
# Also need: sudo apt install ttyd ffmpeg
```

### Use this script

Save as `docs/demo.tape`, then run `vhs docs/demo.tape` → produces `docs/demo.gif`.

```tape
Output docs/demo.gif

Set FontSize 16
Set Width 1200
Set Height 700
Set Theme "GruvboxDark"
Set TypingSpeed 30ms

Type "# 1. install (one-time)"
Enter
Type "pip install primoia-myco"
Sleep 800ms
Enter
Sleep 1.5s

Type "# 2. start the daemon"
Enter
Type "mycod --port 8000 /tmp/myco-demo &"
Sleep 800ms
Enter
Sleep 1.5s

Type "# 3. ALICE asks BOB a question through the myco bus"
Enter
Type "curl -s -X POST http://localhost:8000/events \\"
Enter
Type "  -H 'Authorization: Bearer myco-demo-tenant-token-32chars-min-aaaaa' \\"
Enter
Type "  -d '{\"session\":\"ALICE\",\"events\":[\"ask BOB which-jwt-library\"]}'"
Sleep 800ms
Enter
Sleep 2s

Type "# 4. BOB's panel now shows the pending question"
Enter
Type "curl -s -H 'Authorization: Bearer myco-demo-tenant-token-32chars-min-aaaaa' \\"
Enter
Type "  http://localhost:8000/view/BOB"
Sleep 800ms
Enter
Sleep 3s

Type "# 5. BOB replies — ALICE will see it in her next prompt"
Enter
Type "curl -s -X POST http://localhost:8000/events \\"
Enter
Type "  -H 'Authorization: Bearer myco-demo-tenant-token-32chars-min-aaaaa' \\"
Enter
Type "  -d '{\"session\":\"BOB\",\"events\":[\"reply ALICE use-jose-v5\"]}'"
Sleep 800ms
Enter
Sleep 2s

Type "# 6. The bus did the routing. No copy-paste."
Enter
Sleep 2s
```

Expected output: a polished 25–30s GIF showing the full round-trip. Drop it into `docs/` and link from the README:

```markdown
<p align="center">
  <img src="docs/demo.gif" alt="myco demo: ALICE asks BOB through the swarm bus" width="800">
</p>
```

Place that block right after the badges and before the "Problem/myco is" paragraph.

## Option 2 — `asciinema` (faster, less polish)

If you just want to capture your own real typing and not bother with a script:

```bash
# Install (universal)
pip install asciinema

# Record
asciinema rec docs/demo.cast
# ... do the demo above, then Ctrl+D to stop

# Render to GIF (needs agg from charmbracelet)
# Install: go install github.com/asciinema/agg@latest
agg --theme monokai --font-size 16 docs/demo.cast docs/demo.gif
```

Less control over timing, but works without learning a tape language. Good if you want to ship the demo today and iterate later.

## Tips for whichever tool

- **Keep it under 30 seconds.** GitHub stops auto-playing GIFs after a while; HN scanners give 8 seconds before scrolling.
- **Use a fake/demo token in the script** (the example above uses `myco-demo-tenant-token-32chars-min-aaaaa` — long enough to pass the daemon's entropy check, obviously fake).
- **Don't show real LAN IPs, real tokens, or your `$HOME`.** Use `/tmp/...` paths only.
- **Optimize file size before committing.** GIFs > 5MB make the README slow on mobile. Use `gifsicle -O3 demo.gif -o demo.gif` to shrink.
- **Pin one frame as the OpenGraph social preview** (extract with `ffmpeg -i demo.gif -vframes 1 docs/social-preview.png`) — that's what HN/Twitter/LinkedIn will show when the repo URL is shared.

When done, delete this file and the README will point at the live `docs/demo.gif`.
