#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVERMIND_HOME="${EVERMIND_HOME:-$HOME/.evermind}"
EVEROS_ROOT="$EVERMIND_HOME/everos"
EVERMIND_ARCHIVE_ROOT="${EVERMIND_ARCHIVE_ROOT:-$HOME/BasicMemory}"
SKIP_TOOLCHAIN_INSTALL="${SKIP_TOOLCHAIN_INSTALL:-0}"

info() { printf '[EverMind] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }

render_file() {
  local source="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  python3 - "$source" "$dest" "$PROJECT_ROOT" "$EVEROS_ROOT" "$EVERMIND_ARCHIVE_ROOT" <<'PY'
import sys
source, dest, evermind, everos, basic = sys.argv[1:]
text = open(source, encoding="utf-8").read()
text = text.replace("<EVERMIND_ROOT>", evermind)
text = text.replace("<EVEROS_ROOT>", everos)
text = text.replace("<EVERMIND_ARCHIVE_ROOT>", basic)
open(dest, "w", encoding="utf-8").write(text)
PY
}

bash "$PROJECT_ROOT/scripts/macos/install.sh"
info "Using EverMind built-in local archive and code graph engines."
if [[ "$SKIP_TOOLCHAIN_INSTALL" != "1" ]]; then
  bash "$PROJECT_ROOT/scripts/macos/install-toolchain.sh" --best-effort
fi
bash "$PROJECT_ROOT/scripts/build-vendored-codebase.sh" --best-effort
python3 "$PROJECT_ROOT/scripts/common/render-configs.py" \
  --env-file "$PROJECT_ROOT/.env" \
  --evermind-home "$EVERMIND_HOME" \
  --everos-root "$EVEROS_ROOT" \
  --archive-root "$EVERMIND_ARCHIVE_ROOT" \
  --archive-candidate-dir "$EVERMIND_ARCHIVE_ROOT/.candidates"

GENERATED="$PROJECT_ROOT/generated/mcp-config"
render_file "$PROJECT_ROOT/agents/codex/config-snippet.toml" "$GENERATED/codex.toml"
render_file "$PROJECT_ROOT/agents/claude-code/mcp-config.json" "$GENERATED/claude-code.json"
render_file "$PROJECT_ROOT/agents/cursor/mcp-config.json" "$GENERATED/cursor.json"
render_file "$PROJECT_ROOT/agents/devin/mcp-config.json" "$GENERATED/devin.json"

info "Generated MCP snippets in $GENERATED"
info "No client config files were overwritten."
info "Next: fill model API keys in .env, then run scripts/macos/check-all.sh"

