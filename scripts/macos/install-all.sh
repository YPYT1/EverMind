#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVERMIND_HOME="${EVERMIND_HOME:-$HOME/.evermind}"
EVEROS_ROOT="$EVERMIND_HOME/everos"
BASIC_MEMORY_ROOT="${BASIC_MEMORY_ROOT:-$HOME/BasicMemory}"
TOOLS_ROOT="$EVERMIND_HOME/tools"
CODEBASE_ROOT="$TOOLS_ROOT/codebase-memory-mcp"
SKIP_TOOL_INSTALL="${SKIP_TOOL_INSTALL:-0}"

info() { printf '[EverMind] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }

lock_version() {
  python3 - "$PROJECT_ROOT/third_party.lock.yaml" "$1" <<'PY'
import sys
path, name = sys.argv[1:]
inside = False
for raw in open(path, encoding="utf-8"):
    line = raw.rstrip("\n")
    if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
        inside = line.strip()[:-1] == name
        continue
    if inside and line.startswith("    version:"):
        print(line.split(":", 1)[1].strip().strip('"'))
        break
else:
    raise SystemExit(f"version not found for {name}")
PY
}

render_file() {
  local source="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  python3 - "$source" "$dest" "$PROJECT_ROOT" "$EVEROS_ROOT" "$BASIC_MEMORY_ROOT" <<'PY'
import sys
source, dest, evermind, everos, basic = sys.argv[1:]
text = open(source, encoding="utf-8").read()
text = text.replace("<EVERMIND_ROOT>", evermind)
text = text.replace("<EVEROS_ROOT>", everos)
text = text.replace("<BASIC_MEMORY_ROOT>", basic)
open(dest, "w", encoding="utf-8").write(text)
PY
}

bash "$PROJECT_ROOT/scripts/macos/install.sh"
mkdir -p "$TOOLS_ROOT" "$CODEBASE_ROOT"

if [[ "$SKIP_TOOL_INSTALL" != "1" ]]; then
  command -v uv >/dev/null 2>&1 || { echo "uv was not found. Install uv first."; exit 1; }
  BASIC_VERSION="$(lock_version basic-memory)"
  info "Installing Basic Memory $BASIC_VERSION with uv tool."
  uv tool install "basic-memory==$BASIC_VERSION"

  CODEBASE_VERSION="$(lock_version codebase-memory-mcp)"
  ARCH="$(uname -m)"
  if [[ "$ARCH" == "arm64" ]]; then
    ASSET="codebase-memory-mcp-darwin-arm64.tar.gz"
  else
    ASSET="codebase-memory-mcp-darwin-amd64.tar.gz"
  fi
  URL="https://github.com/DeusData/codebase-memory-mcp/releases/download/$CODEBASE_VERSION/$ASSET"
  ARCHIVE="$CODEBASE_ROOT/$ASSET"
  info "Downloading codebase-memory-mcp $CODEBASE_VERSION."
  curl -L "$URL" -o "$ARCHIVE"
  tar -xzf "$ARCHIVE" -C "$CODEBASE_ROOT"
fi

CODEBASE_BIN="$(find "$CODEBASE_ROOT" -type f -name 'codebase-memory-mcp*' -perm +111 2>/dev/null | head -n 1 || true)"
if [[ -n "$CODEBASE_BIN" ]]; then
  python3 "$PROJECT_ROOT/scripts/common/render-configs.py" \
    --env-file "$PROJECT_ROOT/.env" \
    --evermind-home "$EVERMIND_HOME" \
    --everos-root "$EVEROS_ROOT" \
    --basic-memory-root "$BASIC_MEMORY_ROOT" \
    --candidate-dir "$BASIC_MEMORY_ROOT/.candidates"
  python3 - "$PROJECT_ROOT/.env" "$CODEBASE_BIN" <<'PY'
import sys
path, codebase = sys.argv[1:]
lines = open(path, encoding="utf-8").read().splitlines()
out = []
seen = False
for line in lines:
    if line.startswith("EVERMIND_CODEBASE_MEMORY_PATH="):
        out.append(f"EVERMIND_CODEBASE_MEMORY_PATH={codebase}")
        seen = True
    else:
        out.append(line)
if not seen:
    out.append(f"EVERMIND_CODEBASE_MEMORY_PATH={codebase}")
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
else
  warn "codebase-memory-mcp executable was not found under $CODEBASE_ROOT."
fi

GENERATED="$PROJECT_ROOT/generated/mcp-config"
render_file "$PROJECT_ROOT/agents/codex/config-snippet.toml" "$GENERATED/codex.toml"
render_file "$PROJECT_ROOT/agents/claude-code/mcp-config.json" "$GENERATED/claude-code.json"
render_file "$PROJECT_ROOT/agents/cursor/mcp-config.json" "$GENERATED/cursor.json"
render_file "$PROJECT_ROOT/agents/devin/mcp-config.json" "$GENERATED/devin.json"

info "Generated MCP snippets in $GENERATED"
info "No client config files were overwritten."
info "Next: fill model API keys in .env, then run scripts/macos/check-all.sh"
