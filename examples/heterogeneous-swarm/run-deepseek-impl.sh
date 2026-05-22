#!/bin/bash
# Launches the DEEPSEEK-IMPL session: DeepSeek v4-pro (1M ctx) working in ./impl/.
# Role: read the contract under msg/, implement, reply with ref:.
#
# Trick: ANTHROPIC_BASE_URL/MODEL redirect the `claude` CLI's HTTP calls
# to DeepSeek's Anthropic-compatible endpoint. The launcher and hooks
# are unaware of the swap.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/tenant.env"
mkdir -p "$SCRIPT_DIR/impl"

# === DeepSeek backend ===
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="${DEEPSEEK_API_KEY:?set DEEPSEEK_API_KEY in your shell before running (export DEEPSEEK_API_KEY=sk-...)}"
export ANTHROPIC_MODEL="deepseek-v4-pro"
export ANTHROPIC_SMALL_FAST_MODEL="deepseek-v4-flash"

exec ~/myco/myco DEEPSEEK-IMPL "$SCRIPT_DIR/impl" \
    --daemon "$MYCO_URL" \
    --tenant "$MYCO_TOKEN" \
    "$@"
