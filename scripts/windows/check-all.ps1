param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
)

$ErrorActionPreference = "Stop"
$ok = $true

function Pass($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow; $script:ok = $false }

try {
  & (Join-Path $PSScriptRoot "check.ps1") -ProjectRoot $ProjectRoot
  if (-not $?) { $ok = $false }
} catch {
  Warn "base EverMind checks failed: $($_.Exception.Message)"
}

$envPath = Join-Path $ProjectRoot ".env"
$envText = ""
if (Test-Path -LiteralPath $envPath) {
  $envText = Get-Content -LiteralPath $envPath -Raw
}

if (Get-Command basic-memory -ErrorAction SilentlyContinue) {
  $version = (& basic-memory --version 2>$null | Select-Object -First 1)
  Pass "Basic Memory CLI available $version"
} else {
  Warn "Basic Memory CLI not found; run scripts/windows/install-all.ps1"
}

$codebasePath = ""
if ($envText -match "(?m)^EVERMIND_CODEBASE_MEMORY_PATH=(.+)$") {
  $codebasePath = $Matches[1].Trim()
}
$codebaseCmd = Get-Command codebase-memory-mcp -ErrorAction SilentlyContinue
if ($codebasePath -and (Test-Path -LiteralPath $codebasePath)) {
  Pass "codebase-memory-mcp executable found at $codebasePath"
} elseif ($codebaseCmd) {
  Pass "codebase-memory-mcp available on PATH"
} else {
  Warn "codebase-memory-mcp not found; run scripts/windows/install-all.ps1 or set EVERMIND_CODEBASE_MEMORY_PATH"
}

if ($envText -match "(?m)^BASIC_MEMORY_CANDIDATE_DIR=(.+)$") {
  $candidateDir = $Matches[1].Trim()
  if ($candidateDir -and (Test-Path -LiteralPath $candidateDir)) { Pass "Basic Memory candidate dir exists" } else { Warn "Basic Memory candidate dir missing" }
} else {
  Warn "BASIC_MEMORY_CANDIDATE_DIR missing from .env"
}

$modelVars = @(
  "EVEROS_LLM__API_KEY",
  "EVEROS_MULTIMODAL__API_KEY",
  "EVEROS_EMBEDDING__API_KEY",
  "EVEROS_RERANK__API_KEY"
)
foreach ($name in $modelVars) {
  if ($envText -match "(?m)^$name=.+$") { Pass "$name is set" } else { Warn "$name is empty" }
}

if (Test-Path -LiteralPath (Join-Path $ProjectRoot "generated\mcp-config\codex.toml")) {
  Pass "generated MCP snippets exist"
} else {
  Warn "generated MCP snippets missing; run install-all"
}

if (-not $ok) { exit 1 }
Pass "EverMind full stack checks passed"
