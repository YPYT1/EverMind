#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LEAN_DIR="$PROJECT_ROOT/third_party/codebase-memory-mcp/internal/cbm/vendored/grammars/lean"
TARGET="$LEAN_DIR/parser.c"
CHUNKS_DIR="$LEAN_DIR/parser.c.chunks"
SHA_FILE="$CHUNKS_DIR/parser.c.sha256"
SIZE_FILE="$CHUNKS_DIR/parser.c.size"

info() { printf '[EverMind] %s\n' "$1"; }
pass() { printf '[OK] %s\n' "$1"; }

[[ -f "$SHA_FILE" ]] || { printf '[ERROR] Vendored codebase chunks are missing: %s\n' "$SHA_FILE" >&2; exit 1; }

EXPECTED_HASH="$(awk '{print tolower($1)}' "$SHA_FILE")"
EXPECTED_SIZE="$(tr -d '[:space:]' < "$SIZE_FILE")"

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print tolower($1)}'
  else
    shasum -a 256 "$1" | awk '{print tolower($1)}'
  fi
}

file_size() {
  if stat -c %s "$1" >/dev/null 2>&1; then
    stat -c %s "$1"
  else
    stat -f %z "$1"
  fi
}

if [[ -f "$TARGET" ]]; then
  ACTUAL_SIZE="$(file_size "$TARGET")"
  ACTUAL_HASH="$(sha256_file "$TARGET")"
  if [[ "$ACTUAL_SIZE" == "$EXPECTED_SIZE" && "$ACTUAL_HASH" == "$EXPECTED_HASH" ]]; then
    pass "Vendored codebase lean parser already restored"
    exit 0
  fi
  rm -f "$TARGET"
fi

info "Restoring vendored codebase lean parser from repository chunks"
TMP="$TARGET.tmp"
rm -f "$TMP"
for part in "$CHUNKS_DIR"/parser.c.part*; do
  cat "$part" >> "$TMP"
done

RESTORED_SIZE="$(file_size "$TMP")"
RESTORED_HASH="$(sha256_file "$TMP")"
if [[ "$RESTORED_SIZE" != "$EXPECTED_SIZE" || "$RESTORED_HASH" != "$EXPECTED_HASH" ]]; then
  rm -f "$TMP"
  printf '[ERROR] Restored lean parser failed checksum validation\n' >&2
  exit 1
fi

mv "$TMP" "$TARGET"
pass "Vendored codebase lean parser restored"
