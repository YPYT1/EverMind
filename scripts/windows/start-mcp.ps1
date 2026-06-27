param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
)

$ErrorActionPreference = "Stop"
$mcpRoot = Join-Path $ProjectRoot "mcp"
if (-not (Test-Path -LiteralPath (Join-Path $mcpRoot "pyproject.toml"))) {
  throw "MCP project not found: $mcpRoot"
}

Write-Host "Starting EverMind MCP over stdio from $mcpRoot"
uv run --directory $mcpRoot evermind-mcp


