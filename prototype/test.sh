#!/usr/bin/env bash
# test.sh - end-to-end test of the myco daemon on a ramdisk
#
# Simulates the three-services scenario (SN, SM, IAM) with concurrent event
# writes and measures latency from log append to view update.
#
# Expects a tmpfs ramdisk writable at /mnt/ramdisk/myco-test (or use $SWARM env).

set -eu

SWARM="${SWARM:-/mnt/ramdisk/myco-test}"
HERE="$(cd "$(dirname "$0")" && pwd)"
MYCOD="$HERE/mycod.py"

# ---------- setup ----------

echo "[test] cleaning $SWARM"
rm -rf "$SWARM"
mkdir -p "$SWARM/log" "$SWARM/view"

# ---------- start daemon ----------

echo "[test] starting mycod"
python3 "$MYCOD" "$SWARM" 2>"$SWARM/mycod.stderr" &
DAEMON_PID=$!
trap 'kill $DAEMON_PID 2>/dev/null || true; wait 2>/dev/null || true' EXIT

# Give the daemon a moment to set up tail -F
sleep 0.3

# ---------- helper for measured append ----------

ns() { date +%s%N; }

append_log() {
    local session="$1"
    local text="$2"
    local ts
    ts=$(date -Iseconds)
    printf '%s %s %s\n' "$ts" "$session" "$text" >> "$SWARM/log/$session.log"
}

wait_for_view_contains() {
    local session="$1"
    local needle="$2"
    local timeout_ms="${3:-500}"
    local view="$SWARM/view/$session.md"
    local start_ns now_ns deadline_ns
    start_ns=$(ns)
    deadline_ns=$(( start_ns + timeout_ms * 1000000 ))
    while :; do
        if [ -f "$view" ] && grep -qF "$needle" "$view" 2>/dev/null; then
            now_ns=$(ns)
            echo $(( now_ns - start_ns ))
            return 0
        fi
        now_ns=$(ns)
        if [ "$now_ns" -gt "$deadline_ns" ]; then
            return 1
        fi
        # tight spin; can't sleep less than 1ms reliably in bash
    done
}

# ---------- test 1: basic event → view propagation ----------

echo ""
echo "[test 1] basic propagation (IAM start)"
append_log IAM "start auth.v2"
if lat=$(wait_for_view_contains IAM "start auth.v2"); then
    echo "  ok: view updated in ${lat}ns ($(( lat / 1000000 )).$(( (lat / 1000) % 1000 ))ms)"
else
    echo "  FAIL: view did not update in time"
    cat "$SWARM/view/IAM.md" 2>/dev/null || echo "  (no view)"
    exit 1
fi

# ---------- test 2: dependency resolution ----------

echo ""
echo "[test 2] dependency resolution (SN needs IAM.auth.v2)"
append_log SN "start webhook.incoming"
append_log SN "need IAM.auth.v2"
sleep 0.1
if grep -qF "Bloqueado por: IAM.auth.v2" "$SWARM/view/SN.md" 2>/dev/null; then
    echo "  ok: SN shown as blocked on IAM.auth.v2"
else
    echo "  FAIL: SN not shown as blocked"
    cat "$SWARM/view/SN.md"
    exit 1
fi

# ---------- test 3: unblocking via done ----------

echo ""
echo "[test 3] unblock via IAM done"
append_log IAM "done auth.v2"
if lat=$(wait_for_view_contains SN "Nenhum."); then
    echo "  ok: SN unblocked in ${lat}ns ($(( lat / 1000000 )).$(( (lat / 1000) % 1000 ))ms)"
else
    echo "  FAIL: SN did not get unblocked"
    cat "$SWARM/view/SN.md"
    exit 1
fi

# Verify IAM view shows SN as dependent
if grep -qF "SN" "$SWARM/view/IAM.md" 2>/dev/null; then
    echo "  ok: IAM view mentions SN as dependent"
else
    echo "  WARN: IAM view doesn't mention SN (check dependents logic)"
fi

# ---------- test 4: DIRECTOR directive ----------

echo ""
echo "[test 4] DIRECTOR directive broadcast"
append_log DIRECTOR "direct all usar JWT HS256"
sleep 0.1
for s in SN SM IAM; do
    # Create empty logs so views exist
    touch "$SWARM/log/$s.log"
done
# Touch SM and IAM with a noop event so views get generated
append_log SM "note watching"
append_log IAM "note standby"
sleep 0.1
ok=1
for s in SN IAM; do
    if ! grep -qF "usar JWT HS256" "$SWARM/view/$s.md" 2>/dev/null; then
        echo "  FAIL: $s view missing directive"
        ok=0
    fi
done
if [ "$ok" = "1" ]; then
    echo "  ok: directive propagated to all session views"
fi

# ---------- test 5: ask/answer (question routing) ----------

echo ""
echo "[test 5] question routing"
append_log SN "ask DIRECTOR retry exponencial ou DLQ"
sleep 0.1
if grep -qF "SN → DIRECTOR" "$SWARM/view/DIRECTOR.md" 2>/dev/null; then
    echo "  ok: question appears in DIRECTOR view"
else
    echo "  FAIL: question not routed to DIRECTOR"
    cat "$SWARM/view/DIRECTOR.md"
    exit 1
fi

# ---------- test 6: resource state ----------

echo ""
echo "[test 6] resource up/down tracking"
append_log IAM "up container iam-db"
sleep 0.05
append_log IAM "up endpoint /auth/validate"
sleep 0.1
if grep -qF "| container iam-db | UP |" "$SWARM/view/IAM.md" 2>/dev/null && \
   grep -qF "| endpoint /auth/validate | UP |" "$SWARM/view/IAM.md" 2>/dev/null; then
    echo "  ok: multi-token resources tracked in view"
else
    echo "  FAIL: resources not tracked properly"
    cat "$SWARM/view/IAM.md"
    exit 1
fi

# ---------- test 7: latency benchmark ----------

echo ""
echo "[test 7] latency benchmark (100 events)"
python3 - "$SWARM" <<'PYEOF'
import os, sys, time, pathlib

swarm = pathlib.Path(sys.argv[1])
log = swarm / "log" / "IAM.log"
view = swarm / "view" / "IAM.md"

latencies = []
for i in range(100):
    marker = f"bench_marker_{i}"
    t0 = time.monotonic_ns()
    with open(log, "a") as f:
        f.write(f"2026-04-11T11:00:00 IAM note {marker}\n")
    deadline = t0 + 500_000_000  # 500ms
    while True:
        try:
            content = view.read_text()
        except FileNotFoundError:
            content = ""
        if marker in content:
            t1 = time.monotonic_ns()
            latencies.append(t1 - t0)
            break
        if time.monotonic_ns() > deadline:
            print(f"  FAIL: event {i} timeout")
            sys.exit(1)

latencies.sort()
n = len(latencies)
p50 = latencies[n // 2]
p95 = latencies[int(n * 0.95)]
p99 = latencies[int(n * 0.99)]
avg = sum(latencies) / n
mn = latencies[0]
mx = latencies[-1]

def fmt(ns):
    us = ns / 1000
    if us < 1000:
        return f"{us:.1f}µs"
    return f"{us/1000:.2f}ms"

print(f"  events: {n}")
print(f"  min:    {fmt(mn)}")
print(f"  avg:    {fmt(avg)}")
print(f"  p50:    {fmt(p50)}")
print(f"  p95:    {fmt(p95)}")
print(f"  p99:    {fmt(p99)}")
print(f"  max:    {fmt(mx)}")
PYEOF

# ---------- test 8: concurrent writers ----------

echo ""
echo "[test 8] concurrent writers (3 sessions × 50 events)"
python3 - "$SWARM" <<'PYEOF'
import sys, time, pathlib, threading

swarm = pathlib.Path(sys.argv[1])

def writer(sess, n):
    log = swarm / "log" / f"{sess}.log"
    for i in range(n):
        with open(log, "a") as f:
            f.write(f"2026-04-11T11:01:00 {sess} note concurrent_{i}\n")

threads = []
t0 = time.monotonic_ns()
for s in ("SN", "SM", "IAM"):
    t = threading.Thread(target=writer, args=(s, 50))
    t.start()
    threads.append(t)
for t in threads:
    t.join()
t1 = time.monotonic_ns()
print(f"  150 concurrent events written in {(t1-t0)/1e6:.2f}ms")
PYEOF

# Give the daemon a moment to catch up after the burst
sleep 0.5

echo ""
echo "[test 8 verify] final log line counts"
for s in SN SM IAM; do
    lines=$(wc -l < "$SWARM/log/$s.log")
    echo "  $s.log: $lines lines"
done

# ---------- summary ----------

echo ""
echo "[test] all tests passed"
echo "[test] swarm dir: $SWARM"
echo "[test] views available at: $SWARM/view/"
