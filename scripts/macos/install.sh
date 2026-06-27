#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVERMIND_HOME="${EVERMIND_HOME:-$HOME/.evermind}"
EVEROS_ROOT="$EVERMIND_HOME/everos"
BASIC_MEMORY_ROOT="${BASIC_MEMORY_ROOT:-$HOME/BasicMemory}"
BASIC_MEMORY_CANDIDATE_DIR="$BASIC_MEMORY_ROOT/.candidates"

mkdir -p "$EVEROS_ROOT" "$BASIC_MEMORY_ROOT" "$BASIC_MEMORY_CANDIDATE_DIR"

if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  python3 "$PROJECT_ROOT/scripts/common/render-configs.py" \
    --env-file "$PROJECT_ROOT/.env" \
    --evermind-home "$EVERMIND_HOME" \
    --everos-root "$EVEROS_ROOT" \
    --basic-memory-root "$BASIC_MEMORY_ROOT" \
    --candidate-dir "$BASIC_MEMORY_CANDIDATE_DIR"
fi

echo "EverMind local directories are ready."
echo "Env file: $PROJECT_ROOT/.env"
echo "Next: fill model API keys, then run scripts/macos/check.sh"

