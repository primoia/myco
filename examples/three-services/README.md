# Example: three-services

Three fictional projects that cross paths via APIs, operated by three Claude sessions in parallel, coordinated by myco.

## The three projects

- **SN** — notification service (needs to call SM and IAM)
- **SM** — messaging service (needs IAM for auth)
- **IAM** — identity & access management (independent, but provides auth for the others)

## Natural dependencies

```
    IAM  ──────┐
     │         │
     ▼         ▼
    SM ──────▶ SN
```

- `IAM` publishes `IAM.auth.v2` → unblocks `SM` and `SN`
- `SM` publishes `SM.api.messages` → unblocks `SN`
- `SN` consumes both

## How to run

```bash
# Terminal 1 — daemon
python3 ~/myco/prototype/mycod.py --port 8000 /tmp/myco-swarm

# Terminal 2
~/myco/myco IAM ./IAM

# Terminal 3
~/myco/myco SM ./SM

# Terminal 4
~/myco/myco SN ./SN
```

## The imagined feature

"Send a notification when the user completes onboarding."

This requires:

1. IAM exposes a webhook `user.onboarded`
2. SM consumes the webhook and enqueues a message
3. SN reads from the queue and fires the notification

Without myco: you'd babysit all three Claudes by hand.
With myco: the three coordinate via declarations in the log, and you only intervene if there's a deadlock.
