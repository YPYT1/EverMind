#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OK=1

pass() { printf '[OK] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; OK=0; }

[[ -f "$PROJECT_ROOT/.env" ]] && pass ".env exists" || warn ".env missing; run scripts/macos/install.sh"
command -v uv >/dev/null 2>&1 && pass "uv is available" || warn "uv is not available"
[[ -f "$PROJECT_ROOT/mcp/pyproject.toml" ]] && pass "MCP bridge exists" || warn "MCP bridge missing"
[[ -f "$PROJECT_ROOT/skills/evermind/SKILL.md" ]] && pass "umbrella skill exists" || warn "umbrella skill missing"
[[ -f "$PROJECT_ROOT/templates/evermind-archive-project/项目概览.md" ]] && pass "EverMind Archive templates exist" || warn "EverMind Archive templates missing"

if curl -fsS --max-time 3 http://127.0.0.1:3378/health >/dev/null 2>&1; then
  pass "EverOS health endpoint responded"
else
  warn "EverOS health endpoint did not respond"
fi

if grep -R "D:\\\\" \
  "$PROJECT_ROOT/templates/mcp-config/codex.macos.toml" \
  "$PROJECT_ROOT/templates/mcp-config/claude-code.macos.json" \
  "$PROJECT_ROOT/templates/mcp-config/cursor.macos.json" \
  "$PROJECT_ROOT/agents" \
  "$PROJECT_ROOT/config" >/dev/null 2>&1; then
  warn "Windows path appears in macOS or generic template area"
else
  pass "no Windows paths in generic template areas"
fi

[[ "$OK" -eq 1 ]] || exit 1
pass "EverMind checks passed"


