#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
EVERMIND_HOME="${EVERMIND_HOME:-$HOME/.evermind}"
USER_HOME="${USER_HOME:-$HOME}"
NON_INTERACTIVE="${NON_INTERACTIVE:-0}"
COPY_INSTEAD_OF_SYMLINK="${COPY_INSTEAD_OF_SYMLINK:-0}"
RUN_CHECKS="${RUN_CHECKS:-0}"
LLM_API_KEY="${LLM_API_KEY:-}"
MULTIMODAL_API_KEY="${MULTIMODAL_API_KEY:-}"
EMBEDDING_API_KEY="${EMBEDDING_API_KEY:-}"
RERANK_API_KEY="${RERANK_API_KEY:-}"

info() { printf '[EverMind] %s\n' "$1"; }

set_env_line() {
  local env_path="$1"
  local name="$2"
  local value="$3"
  [[ -n "$value" ]] || return 0
  python3 - "$env_path" "$name" "$value" <<'PY'
import sys
path, name, value = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines()
out = []
seen = False
for line in lines:
    if line.startswith(f"{name}="):
        out.append(f"{name}={value}")
        seen = True
    else:
        out.append(line)
if not seen:
    out.append(f"{name}={value}")
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
}

if [[ "$NON_INTERACTIVE" != "1" ]]; then
  read -r -p "EverMind runtime directory [$EVERMIND_HOME]: " home_input
  [[ -z "$home_input" ]] || EVERMIND_HOME="$home_input"
  read -r -p "LLM API key (blank to skip): " LLM_API_KEY
  read -r -p "Multimodal API key (blank to skip): " MULTIMODAL_API_KEY
  read -r -p "Embedding API key (blank to skip): " EMBEDDING_API_KEY
  read -r -p "Rerank API key (blank to skip): " RERANK_API_KEY
fi

info "Preparing local runtime and generated MCP config."
EVERMIND_HOME="$EVERMIND_HOME" bash "$PROJECT_ROOT/scripts/macos/install-all.sh"

ENV_PATH="$PROJECT_ROOT/.env"
set_env_line "$ENV_PATH" "EVEROS_LLM__API_KEY" "$LLM_API_KEY"
set_env_line "$ENV_PATH" "EVEROS_MULTIMODAL__API_KEY" "$MULTIMODAL_API_KEY"
set_env_line "$ENV_PATH" "EVEROS_EMBEDDING__API_KEY" "$EMBEDDING_API_KEY"
set_env_line "$ENV_PATH" "EVEROS_RERANK__API_KEY" "$RERANK_API_KEY"

info "Installing EverMind skills into user skill folders."
USER_HOME="$USER_HOME" COPY_INSTEAD_OF_SYMLINK="$COPY_INSTEAD_OF_SYMLINK" bash "$PROJECT_ROOT/scripts/macos/setup-user.sh"

if [[ "$RUN_CHECKS" == "1" ]]; then
  info "Running full stack checks."
  bash "$PROJECT_ROOT/scripts/macos/check-all.sh"
fi

info "Configuration complete."
info "Generated MCP config: $PROJECT_ROOT/generated/mcp-config"
info "No existing Codex, Claude Code, Cursor, or Devin config was overwritten."
