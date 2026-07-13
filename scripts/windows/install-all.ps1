param(
  [string]$EverMindHome = "D:\EverMindMemory",
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path,
  [switch]$SkipToolchainInstall
)

$ErrorActionPreference = "Stop"

function Info($msg) { Write-Host "[EverMind] $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

function Render-File {
  param(
    [string]$Source,
    [string]$Destination,
    [hashtable]$Values
  )
  $text = Get-Content -LiteralPath $Source -Raw
  foreach ($key in $Values.Keys) {
    $text = $text.Replace($key, $Values[$key])
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
  Set-Content -LiteralPath $Destination -Value $text -Encoding UTF8
}

& (Join-Path $PSScriptRoot "install.ps1") -EverMindHome $EverMindHome -ProjectRoot $ProjectRoot

$basicRoot = Join-Path $EverMindHome "evermind-archive"
Info "Using EverMind built-in local archive and code graph engines."
if (-not $SkipToolchainInstall) {
  & (Join-Path $PSScriptRoot "install-toolchain.ps1") -BestEffort
}
& (Join-Path $ProjectRoot "scripts\build-vendored-codebase.ps1") -ProjectRoot $ProjectRoot -BestEffort

$generated = Join-Path $ProjectRoot "generated\mcp-config"
$values = @{
  "<EVERMIND_ROOT>" = $ProjectRoot.Replace("\", "/")
  "<EVERMIND_ARCHIVE_ROOT>" = $basicRoot.Replace("\", "/")
}

Render-File -Source (Join-Path $ProjectRoot "agents\codex\config-snippet.toml") -Destination (Join-Path $generated "codex.toml") -Values $values
Render-File -Source (Join-Path $ProjectRoot "agents\claude-code\mcp-config.json") -Destination (Join-Path $generated "claude-code.json") -Values $values
Render-File -Source (Join-Path $ProjectRoot "agents\cursor\mcp-config.json") -Destination (Join-Path $generated "cursor.json") -Values $values
Render-File -Source (Join-Path $ProjectRoot "agents\devin\mcp-config.json") -Destination (Join-Path $generated "devin.json") -Values $values

Info "Generated MCP snippets in $generated"
Info "No client config files were overwritten."
Info "Next: fill model API keys in .env, then run scripts/windows/check-all.ps1"

