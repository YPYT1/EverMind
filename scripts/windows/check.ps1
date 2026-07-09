param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
)

$ErrorActionPreference = "Stop"
$ok = $true

function Pass($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow; $script:ok = $false }
function InfoWarn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

if (Test-Path -LiteralPath (Join-Path $ProjectRoot ".env")) { Pass ".env exists" } else { Warn ".env missing; run scripts/windows/install.ps1" }
if (Get-Command uv -ErrorAction SilentlyContinue) { Pass "uv is available" } else { Warn "uv is not available" }
if (Test-Path -LiteralPath (Join-Path $ProjectRoot "mcp\pyproject.toml")) { Pass "MCP bridge exists" } else { Warn "MCP bridge missing" }
if (Test-Path -LiteralPath (Join-Path $ProjectRoot "skills\evermind\SKILL.md")) { Pass "umbrella skill exists" } else { Warn "umbrella skill missing" }
if (Test-Path -LiteralPath (Join-Path $ProjectRoot "templates\evermind-archive-project\项目概览.md")) { Pass "EverMind Archive templates exist" } else { Warn "EverMind Archive templates missing" }

$conn = Get-NetTCPConnection -LocalPort 3378 -State Listen -ErrorAction SilentlyContinue
if ($conn) { Pass "port 3378 is listening" } else { InfoWarn "port 3378 is not listening; EverOS is optional for EverMind MCP v2" }

try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:3378/health" -TimeoutSec 3
  Pass "EverOS health endpoint responded"
} catch {
  InfoWarn "EverOS health endpoint did not respond; EverMind MCP v2 can still use embedded SQLite"
}

if (-not $ok) { exit 1 }
Pass "EverMind checks passed"



