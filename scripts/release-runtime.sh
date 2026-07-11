#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CODEBASE_BINARY="${CODEBASE_BINARY:-}"
OUTPUT_DIRECTORY="${OUTPUT_DIRECTORY:-$PROJECT_ROOT/dist/runtime}"
TARGET="${TARGET:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    --codebase-binary) CODEBASE_BINARY="$2"; shift 2 ;;
    --output-directory) OUTPUT_DIRECTORY="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    *) printf '[ERROR] unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [[ -z "$CODEBASE_BINARY" ]]; then
  bash "$PROJECT_ROOT/scripts/build-vendored-codebase.sh"
  CODEBASE_BINARY="$PROJECT_ROOT/third_party/codebase-memory-mcp/build/c/codebase-memory-mcp"
fi
[[ -f "$CODEBASE_BINARY" ]] || {
  printf '[ERROR] codebase engine binary not found: %s\n' "$CODEBASE_BINARY" >&2
  exit 1
}

ARGS=(
  run --frozen --directory "$PROJECT_ROOT/mcp" python -m scripts.release_runtime_bundle
  --repo-root "$PROJECT_ROOT"
  --codebase-binary "$CODEBASE_BINARY"
  --output-directory "$OUTPUT_DIRECTORY"
)
if [[ -n "$TARGET" ]]; then
  ARGS+=(--target "$TARGET")
fi

exec uv "${ARGS[@]}"
