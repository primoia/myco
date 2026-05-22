#!/bin/bash
# Launches CLAUDE-DUEL: Claude (default model) in the claude-arena/ directory.
# Uses the same tenant as the parent example — both duelists see each other in the panel.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/../tenant.env"
mkdir -p "$SCRIPT_DIR/claude-arena"

exec ~/myco/myco CLAUDE-DUEL "$SCRIPT_DIR/claude-arena" \
    --daemon "$MYCO_URL" \
    --tenant "$MYCO_TOKEN" \
    "$@"
