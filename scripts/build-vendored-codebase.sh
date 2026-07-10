#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BEST_EFFORT=0
if [[ "${1:-}" == "--best-effort" ]]; then
  BEST_EFFORT=1
fi

info() { printf '[EverMind] %s\n' "$1"; }
pass() { printf '[OK] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }
stop_or_warn() {
  if [[ "$BEST_EFFORT" -eq 1 ]]; then
    warn "$1"
    exit 0
  fi
  printf '[ERROR] %s\n' "$1" >&2
  exit 1
}

SOURCE="$PROJECT_ROOT/third_party/codebase-memory-mcp"
MAKEFILE="$SOURCE/Makefile.cbm"
BINARY="$SOURCE/build/c/codebase-memory-mcp"

[[ -f "$MAKEFILE" ]] || stop_or_warn "Vendored codebase-memory-mcp source is missing: $SOURCE"
bash "$PROJECT_ROOT/scripts/restore-vendored-codebase.sh"
[[ ! -x "$BINARY" ]] || { pass "Vendored codebase-memory-mcp binary already built"; exit 0; }
command -v make >/dev/null 2>&1 || stop_or_warn "make not found. Install make plus clang/gcc, then rerun scripts/build-vendored-codebase.sh."
if ! command -v clang >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1 && ! command -v cc >/dev/null 2>&1; then
  stop_or_warn "C compiler not found. Install clang/gcc, then rerun scripts/build-vendored-codebase.sh."
fi

info "Building vendored codebase-memory-mcp from source"
(cd "$SOURCE" && make -f Makefile.cbm cbm)
[[ -x "$BINARY" ]] || stop_or_warn "Build completed but binary was not found under third_party/codebase-memory-mcp/build/c"
pass "Vendored codebase-memory-mcp built successfully"
