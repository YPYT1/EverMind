#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MCP_ROOT="$PROJECT_ROOT/mcp"

echo "Starting EverMind MCP over stdio from $MCP_ROOT"
uv run --directory "$MCP_ROOT" evermemos-mcp

