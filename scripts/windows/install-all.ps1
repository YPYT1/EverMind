param(
  [string]$EverMindHome = "D:\EverMindMemory",
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path,
  [switch]$SkipToolInstall
)

$ErrorActionPreference = "Stop"

function Info($msg) { Write-Host "[EverMind] $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

$archiveEngineVersion = "0.22.1"
$codeGraphEngineVersion = "v0.9.0"

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

$everosRoot = Join-Path $EverMindHome "everos"
$basicRoot = Join-Path $EverMindHome "evermind-archive"
$toolsRoot = Join-Path $EverMindHome "tools"
$codebaseRoot = Join-Path $toolsRoot "evermind-code-graph"
New-Item -ItemType Directory -Force -Path $toolsRoot, $codebaseRoot | Out-Null

if (-not $SkipToolInstall) {
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found. Install uv first, then rerun install-all.ps1."
  }

  Info "Installing EverMind Archive $archiveEngineVersion with uv tool."
  & uv tool install "basic-memory==$archiveEngineVersion"
  if ($LASTEXITCODE -ne 0) { throw "EverMind Archive install failed." }

  $codebaseExePath = Join-Path $codebaseRoot "codebase-memory-mcp.exe"
  $url = "https://github.com/DeusData/codebase-memory-mcp/releases/download/$codeGraphEngineVersion/codebase-memory-mcp-windows-amd64.exe"
  Info "Downloading EverMind Code Graph $codeGraphEngineVersion."
  Invoke-WebRequest -Uri $url -OutFile $codebaseExePath
}

$codebaseExe = Get-ChildItem -LiteralPath $codebaseRoot -Recurse -File -Filter "codebase-memory-mcp*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($codebaseExe) {
  $envPath = Join-Path $ProjectRoot ".env"
  $text = Get-Content -LiteralPath $envPath -Raw
  $text = $text -replace "(?m)^#?\s*EVERMIND_CODEBASE_MEMORY_PATH=.*$", "EVERMIND_CODEBASE_MEMORY_PATH=$($codebaseExe.FullName)"
  Set-Content -LiteralPath $envPath -Value $text -Encoding UTF8
} else {
  Warn "EverMind Code Graph executable was not found under $codebaseRoot. check-all will report this until installed."
}

$generated = Join-Path $ProjectRoot "generated\mcp-config"
$values = @{
  "<EVERMIND_ROOT>" = $ProjectRoot.Replace("\", "/")
  "<EVEROS_ROOT>" = $everosRoot.Replace("\", "/")
  "<EVERMIND_ARCHIVE_ROOT>" = $basicRoot.Replace("\", "/")
}

Render-File -Source (Join-Path $ProjectRoot "agents\codex\config-snippet.toml") -Destination (Join-Path $generated "codex.toml") -Values $values
Render-File -Source (Join-Path $ProjectRoot "agents\claude-code\mcp-config.json") -Destination (Join-Path $generated "claude-code.json") -Values $values
Render-File -Source (Join-Path $ProjectRoot "agents\cursor\mcp-config.json") -Destination (Join-Path $generated "cursor.json") -Values $values
Render-File -Source (Join-Path $ProjectRoot "agents\devin\mcp-config.json") -Destination (Join-Path $generated "devin.json") -Values $values

Info "Generated MCP snippets in $generated"
Info "No client config files were overwritten."
Info "Next: fill model API keys in .env, then run scripts/windows/check-all.ps1"

