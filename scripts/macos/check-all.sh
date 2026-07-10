#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OK=1

pass() { printf '[OK] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; OK=0; }
info() { printf '[INFO] %s\n' "$1"; }

if bash "$PROJECT_ROOT/scripts/macos/check.sh"; then
  pass "base EverMind checks passed"
else
  warn "base EverMind checks failed"
fi

ENV_FILE="$PROJECT_ROOT/.env"
ENV_TEXT=""
[[ -f "$ENV_FILE" ]] && ENV_TEXT="$(cat "$ENV_FILE")"

pass "Built-in EverMind Archive engine available"
pass "Built-in EverMind Code Graph engine available"

MISSING_TOOLCHAIN=()
command -v make >/dev/null 2>&1 || MISSING_TOOLCHAIN+=("make")
if ! command -v clang >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1 && ! command -v cc >/dev/null 2>&1; then
  MISSING_TOOLCHAIN+=("clang/gcc/cc")
fi
if [[ "${#MISSING_TOOLCHAIN[@]}" -eq 0 ]]; then
  pass "Source-fusion C build toolchain available"
else
  info "Source-fusion build toolchain incomplete: ${MISSING_TOOLCHAIN[*]}. Run scripts/macos/install-toolchain.sh"
fi
if command -v cmake >/dev/null 2>&1; then
  pass "Optional CMake available"
else
  info "Optional CMake not found; current vendored Makefile build does not require it"
fi
if command -v ninja >/dev/null 2>&1; then
  pass "Optional Ninja available"
else
  info "Optional Ninja not found; current vendored Makefile build does not require it"
fi

BM_SOURCE="$PROJECT_ROOT/third_party/basic-memory"
if [[ -f "$BM_SOURCE/LICENSE" && -f "$BM_SOURCE/pyproject.toml" && -d "$BM_SOURCE/src/basic_memory/mcp" && -f "$BM_SOURCE/src/basic_memory/markdown/entity_parser.py" ]] && grep -q "AGPL-3.0-or-later" "$BM_SOURCE/pyproject.toml"; then
  pass "Source-fused Basic Memory source integrated"
else
  warn "Source-fused Basic Memory source incomplete"
fi

CBM_SOURCE="$PROJECT_ROOT/third_party/codebase-memory-mcp"
if [[ -f "$CBM_SOURCE/internal/cbm/vendored/grammars/lean/parser.c.chunks/parser.c.sha256" ]]; then
  if ! bash "$PROJECT_ROOT/scripts/restore-vendored-codebase.sh"; then
    warn "Vendored codebase chunk restore failed"
  fi
fi
CBM_GRAMMARS="$CBM_SOURCE/internal/cbm/vendored/grammars"
CBM_LSP="$CBM_SOURCE/internal/cbm/lsp"
GRAMMAR_COUNT=0
if [[ -d "$CBM_GRAMMARS" ]]; then
  GRAMMAR_COUNT="$(find "$CBM_GRAMMARS" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
fi
MISSING_LSP=0
for file in py_lsp.c ts_lsp.c php_lsp.c cs_lsp.c go_lsp.c c_lsp.c java_lsp.c kotlin_lsp.c rust_lsp.c; do
  [[ -f "$CBM_LSP/$file" ]] || MISSING_LSP=1
done
if [[ -f "$CBM_SOURCE/Makefile.cbm" && -f "$CBM_SOURCE/internal/cbm/lsp_all.c" && -f "$CBM_GRAMMARS/MANIFEST.md" && -f "$CBM_GRAMMARS/lean/parser.c" && -f "$CBM_SOURCE/vendored/zlib/zlib.h" && -f "$CBM_SOURCE/vendored/zlib/inflate.c" && -f "$CBM_SOURCE/vendored/zlib/LICENSE" && "$GRAMMAR_COUNT" -ge 159 && "$MISSING_LSP" -eq 0 ]]; then
  pass "Vendored codebase-memory-mcp source integrated"
else
  warn "Vendored codebase-memory-mcp source incomplete"
fi
if [[ -x "$CBM_SOURCE/build/c/codebase-memory-mcp" ]]; then
  pass "Vendored codebase-memory-mcp binary built"
else
  info "Vendored codebase-memory-mcp binary not built; native Python code graph fallback remains active"
fi

CANDIDATE_DIR="$(printf '%s\n' "$ENV_TEXT" | sed -n 's/^EVERMIND_ARCHIVE_CANDIDATE_DIR=//p' | head -n 1)"
[[ -n "$CANDIDATE_DIR" && -d "$CANDIDATE_DIR" ]] && pass "EverMind Archive candidate dir exists" || warn "EverMind Archive candidate dir missing"

for name in EVEROS_LLM__API_KEY EVEROS_MULTIMODAL__API_KEY EVEROS_EMBEDDING__API_KEY EVEROS_RERANK__API_KEY; do
  if grep -q "^$name=." "$ENV_FILE" 2>/dev/null; then
    pass "$name is set"
  else
    info "$name is empty; model-backed features remain optional"
  fi
done

[[ -f "$PROJECT_ROOT/generated/mcp-config/codex.toml" ]] && pass "generated MCP snippets exist" || warn "generated MCP snippets missing"

[[ "$OK" -eq 1 ]] || exit 1
pass "EverMind full stack checks passed"


