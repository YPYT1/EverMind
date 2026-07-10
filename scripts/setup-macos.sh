#!/usr/bin/env bash
set -euo pipefail

# EverMind v2 Setup Script - macOS
# Usage: bash scripts/setup-macos.sh
# Or:    chmod +x scripts/setup-macos.sh && ./scripts/setup-macos.sh

# ─── Helper functions ────────────────────────────────────────────────────────

header() { echo; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; echo "  $1"; echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; }
ok()     { echo "  ✅  $1"; }
warn()   { echo "  ⚠️   $1"; }
fail()   { echo "  ❌  $1"; exit 1; }
step()   { echo "  →   $1"; }

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# ─── Section 1: Environment Detection ────────────────────────────────────────

header "EverMind v2 - Environment Detection"

# a) Python check
PYTHON_CMD=""
for candidate in python3 python; do
  if command -v "$candidate" &>/dev/null; then
    ver=$("$candidate" -c "import sys; v=sys.version_info; print(v.major*100+v.minor)" 2>/dev/null || echo 0)
    if [ "$ver" -ge 311 ]; then
      PYTHON_CMD="$candidate"
      ok "Python $($candidate --version)"
      break
    fi
  fi
done
[ -n "$PYTHON_CMD" ] || fail "Python 3.11+ required. Install from https://www.python.org or via Homebrew: brew install python@3.12"

# b) uv check
if ! command -v uv &>/dev/null; then
  warn "uv not found"
  read -r -p "  Install uv now? [Y/n] " ans
  if [[ "${ans:-Y}" =~ ^[Yy] ]]; then
    step "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    source "$HOME/.cargo/env" 2>/dev/null || true
  fi
fi
command -v uv &>/dev/null && ok "uv: $(uv --version)" || fail "uv not found after install attempt. Add ~/.local/bin or ~/.cargo/bin to PATH and re-run."

# c) git check
if command -v git &>/dev/null; then
  ok "git: $(git --version)"
else
  warn "git not found (optional but recommended)"
fi

# d) sentence-transformers check
if "$PYTHON_CMD" -c "import sentence_transformers" 2>/dev/null; then
  ok "sentence-transformers: installed"
else
  warn "sentence-transformers not installed (optional, enables semantic search). Install: cd mcp && uv pip install sentence-transformers"
fi

# e) sqlite-vec check
if "$PYTHON_CMD" -c "import sqlite_vec" 2>/dev/null; then
  ok "sqlite-vec: installed"
else
  warn "sqlite-vec not installed (optional, enables vector search). Install: cd mcp && uv pip install sqlite-vec"
fi

# ─── Section 2: Install EverMind ─────────────────────────────────────────────

header "Installing EverMind MCP Server"

MCP_DIR="$SCRIPT_DIR/../mcp"
MCP_DIR=$(cd "$MCP_DIR" 2>/dev/null && pwd) || fail "mcp directory not found. Run this script from the EverMind root directory."
[ -d "$MCP_DIR" ] || fail "mcp directory not found at: $MCP_DIR"

step "Installing EverMind + all dependencies (sqlite-vec, sentence-transformers)..."
uv sync --directory "$MCP_DIR" --extra full || fail "uv sync failed. Check the error above."
ok "EverMind MCP server installed"

step "Running smoke test..."
uv run --directory "$MCP_DIR" python -c "from evermind_mcp.config_v2 import load_config; from evermind_mcp.storage import EmbeddedStorage; import pathlib, tempfile; tmp=tempfile.mkdtemp(); cfg=load_config(); s=EmbeddedStorage(pathlib.Path(tmp)/'test.db'); s.close_all(); print('ok')" \
  && ok "Import test passed" \
  || fail "Import test failed. Run: uv sync --directory mcp"

# ─── Section 3: Configure Built-in Engines ───────────────────────────────────

header "Configuring Built-in Code Graph and Archive Engines"

EVERMIND_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
bash "$EVERMIND_ROOT/scripts/macos/install-all.sh"
ok "Built-in engines configured. Users register only the evermind MCP server."

# ─── Section 4: Detect Config Paths ──────────────────────────────────────────

header "Detecting Platform Config Paths"

CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
CURSOR_CONFIG_1="$HOME/Library/Application Support/Cursor/User/globalStorage/cursor.mcp/mcp.json"
CURSOR_CONFIG_2="$HOME/.cursor/mcp.json"

# ─── Section 4: Configure Claude Desktop and Cursor ──────────────────────────

update_mcp_config() {
  local config_path="$1"
  local app_name="$2"
  local evermind_root="$3"

  if [ -f "$config_path" ]; then
    step "Updating $config_path"
    "$PYTHON_CMD" - "$config_path" "$evermind_root" <<'PYEOF'
import sys, json, os

config_path = sys.argv[1]
evermind_root = sys.argv[2]

with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

config.setdefault("mcpServers", {})
config["mcpServers"]["evermind"] = {
    "command": "uv",
    "args": ["run", "--directory", os.path.join(evermind_root, "mcp"), "evermind-mcp"]
}

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PYEOF
    ok "Updated $config_path"
    step "Restart $app_name to apply changes"

  elif [ -d "$(dirname "$config_path")" ]; then
    step "Creating $config_path"
    "$PYTHON_CMD" - "$config_path" "$evermind_root" <<'PYEOF'
import sys, json, os

config_path = sys.argv[1]
evermind_root = sys.argv[2]

config = {
    "mcpServers": {
        "evermind": {
            "command": "uv",
            "args": ["run", "--directory", os.path.join(evermind_root, "mcp"), "evermind-mcp"]
        }
    }
}

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)
    f.write("\n")
PYEOF
    ok "Created $config_path"
    step "Restart $app_name to apply changes"

  else
    warn "$app_name config not found at: $config_path"
    echo
    echo "  Add the following to your $app_name MCP config manually:"
    echo
    cat <<SNIPPET
  {
    "mcpServers": {
      "evermind": {
        "command": "uv",
        "args": ["run", "--directory", "${evermind_root}/mcp", "evermind-mcp"]
      }
    }
  }
SNIPPET
    echo
  fi
}

# Claude Desktop
update_mcp_config "$CLAUDE_CONFIG" "Claude Desktop" "$EVERMIND_ROOT"

# Cursor: prefer the first config path, fall back to the second
if [ -f "$CURSOR_CONFIG_1" ] || [ -d "$(dirname "$CURSOR_CONFIG_1")" ]; then
  update_mcp_config "$CURSOR_CONFIG_1" "Cursor" "$EVERMIND_ROOT"
else
  update_mcp_config "$CURSOR_CONFIG_2" "Cursor" "$EVERMIND_ROOT"
fi

# ─── Section 5: Memory Directory ─────────────────────────────────────────────

header "Memory Directory"
mkdir -p "$HOME/.evermind"
ok "Memory directory: $HOME/.evermind"

# ─── Section 6: Summary ──────────────────────────────────────────────────────

header "Setup Complete"
echo
echo "  EverMind v2 is installed and configured."
echo
echo "  Next steps:"
echo "  1. Restart Claude Desktop or Cursor"
echo
echo "  Step 2 — Add the EverMind skill to your project:"
echo
echo "  Add this line to your project's CLAUDE.md or AGENTS.md:"
echo
echo "    \$\${EVERMIND_ROOT}/skills/evermind/SKILL.md"
echo
echo "  This tells Claude Code when and how to use EverMind memory."
echo
echo "  Or copy agents/claude-code/CLAUDE.md as a starting template."
echo
echo "  Optional - enable vector search (much better semantic recall):"
echo "  cd mcp && uv pip install sqlite-vec sentence-transformers"
echo
echo "  Docs: https://github.com/YPYT1/EverMind"
echo
