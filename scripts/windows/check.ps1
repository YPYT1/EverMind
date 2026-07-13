param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
)

$ErrorActionPreference = "Stop"
$ok = $true

function Pass($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow; $script:ok = $false }

if (Test-Path -LiteralPath (Join-Path $ProjectRoot ".env")) { Pass ".env exists" } else { Warn ".env missing; run scripts/windows/install.ps1" }
if (Get-Command uv -ErrorAction SilentlyContinue) { Pass "uv is available" } else { Warn "uv is not available" }
if (Test-Path -LiteralPath (Join-Path $ProjectRoot "mcp\pyproject.toml")) { Pass "MCP interface exists" } else { Warn "MCP interface missing" }
if (Test-Path -LiteralPath (Join-Path $ProjectRoot "skills\evermind\SKILL.md")) { Pass "umbrella skill exists" } else { Warn "umbrella skill missing" }
if (Test-Path -LiteralPath (Join-Path $ProjectRoot "templates\evermind-archive-project\项目概览.md")) { Pass "EverMind Archive templates exist" } else { Warn "EverMind Archive templates missing" }

if (-not $ok) { exit 1 }
Pass "EverMind checks passed"



