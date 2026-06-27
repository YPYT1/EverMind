#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVERMIND_HOME="${EVERMIND_HOME:-$HOME/.evermind}"
EVEROS_ROOT="$EVERMIND_HOME/everos"
EVERMIND_ARCHIVE_ROOT="${EVERMIND_ARCHIVE_ROOT:-$HOME/BasicMemory}"
EVERMIND_ARCHIVE_CANDIDATE_DIR="$EVERMIND_ARCHIVE_ROOT/.candidates"

mkdir -p "$EVEROS_ROOT" "$EVERMIND_ARCHIVE_ROOT" "$EVERMIND_ARCHIVE_CANDIDATE_DIR"

if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
  cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
  python3 "$PROJECT_ROOT/scripts/common/render-configs.py" \
    --env-file "$PROJECT_ROOT/.env" \
    --evermind-home "$EVERMIND_HOME" \
    --everos-root "$EVEROS_ROOT" \
    --archive-root "$EVERMIND_ARCHIVE_ROOT" \
    --archive-candidate-dir "$EVERMIND_ARCHIVE_CANDIDATE_DIR"
fi

echo "EverMind local directories are ready."
echo "Env file: $PROJECT_ROOT/.env"
echo "Next: fill model API keys, then run scripts/macos/check.sh"


