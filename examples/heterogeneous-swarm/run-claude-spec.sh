#!/bin/bash
# Launches the CLAUDE-SPEC session: Claude (default model) working in ./spec/.
# Role: write the contract under msg/, ask the peer, review what DEEPSEEK-IMPL returns.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/tenant.env"
mkdir -p "$SCRIPT_DIR/spec"

exec ~/myco/myco CLAUDE-SPEC "$SCRIPT_DIR/spec" \
    --daemon "$MYCO_URL" \
    --tenant "$MYCO_TOKEN" \
    "$@"
