#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OK=1

pass() { printf '[OK] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; OK=0; }

if bash "$PROJECT_ROOT/scripts/macos/check.sh"; then
  pass "base EverMind checks passed"
else
  warn "base EverMind checks failed"
fi

ENV_FILE="$PROJECT_ROOT/.env"
ENV_TEXT=""
[[ -f "$ENV_FILE" ]] && ENV_TEXT="$(cat "$ENV_FILE")"

command -v basic-memory >/dev/null 2>&1 && pass "Basic Memory CLI available" || warn "Basic Memory CLI not found"

CODEBASE_PATH="$(printf '%s\n' "$ENV_TEXT" | sed -n 's/^EVERMIND_CODEBASE_MEMORY_PATH=//p' | head -n 1)"
if [[ -n "$CODEBASE_PATH" && -x "$CODEBASE_PATH" ]]; then
  pass "codebase-memory-mcp executable found at $CODEBASE_PATH"
elif command -v codebase-memory-mcp >/dev/null 2>&1; then
  pass "codebase-memory-mcp available on PATH"
else
  warn "codebase-memory-mcp not found"
fi

CANDIDATE_DIR="$(printf '%s\n' "$ENV_TEXT" | sed -n 's/^BASIC_MEMORY_CANDIDATE_DIR=//p' | head -n 1)"
[[ -n "$CANDIDATE_DIR" && -d "$CANDIDATE_DIR" ]] && pass "Basic Memory candidate dir exists" || warn "Basic Memory candidate dir missing"

for name in EVEROS_LLM__API_KEY EVEROS_MULTIMODAL__API_KEY EVEROS_EMBEDDING__API_KEY EVEROS_RERANK__API_KEY; do
  if grep -q "^$name=." "$ENV_FILE" 2>/dev/null; then
    pass "$name is set"
  else
    warn "$name is empty"
  fi
done

[[ -f "$PROJECT_ROOT/generated/mcp-config/codex.toml" ]] && pass "generated MCP snippets exist" || warn "generated MCP snippets missing"

[[ "$OK" -eq 1 ]] || exit 1
pass "EverMind full stack checks passed"

