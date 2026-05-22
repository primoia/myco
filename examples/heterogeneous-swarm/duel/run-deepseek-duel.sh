#!/bin/bash
# Launches DEEPSEEK-DUEL: deepseek-v4-pro in the deepseek-arena/ directory.
# Uses the same tenant as the parent example.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../tenant.env"
mkdir -p "$SCRIPT_DIR/deepseek-arena"

# === DeepSeek backend ===
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
export ANTHROPIC_AUTH_TOKEN="${DEEPSEEK_API_KEY:?set DEEPSEEK_API_KEY in your shell before running (export DEEPSEEK_API_KEY=sk-...)}"
export ANTHROPIC_MODEL="deepseek-v4-pro"
export ANTHROPIC_SMALL_FAST_MODEL="deepseek-v4-flash"

exec ~/myco/myco DEEPSEEK-DUEL "$SCRIPT_DIR/deepseek-arena" \
    --daemon "$MYCO_URL" \
    --tenant "$MYCO_TOKEN" \
    "$@"
