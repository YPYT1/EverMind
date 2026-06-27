param(
  [string]$EverMindHome = "D:\EverMindMemory",
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
)

$ErrorActionPreference = "Stop"

$everosRoot = Join-Path $EverMindHome "everos"
$basicRoot = Join-Path $EverMindHome "evermind-archive"
$candidateDir = Join-Path $basicRoot ".candidates"

New-Item -ItemType Directory -Force -Path $everosRoot, $basicRoot, $candidateDir | Out-Null

$envPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
  Copy-Item -LiteralPath (Join-Path $ProjectRoot ".env.example") -Destination $envPath
  $text = Get-Content -LiteralPath $envPath -Raw
  $text = $text -replace "(?m)^EVERMIND_HOME=.*$", "EVERMIND_HOME=$EverMindHome"
  $text = $text -replace "(?m)^EVEROS_ROOT=.*$", "EVEROS_ROOT=$everosRoot"
  $text = $text -replace "(?m)^EVERMIND_ARCHIVE_ROOT=.*$", "EVERMIND_ARCHIVE_ROOT=$basicRoot"
  $text = $text -replace "(?m)^EVERMIND_ARCHIVE_CANDIDATE_DIR=.*$", "EVERMIND_ARCHIVE_CANDIDATE_DIR=$candidateDir"
  Set-Content -LiteralPath $envPath -Value $text -Encoding UTF8
}

Write-Host "EverMind local directories are ready."
Write-Host "Env file: $envPath"
Write-Host "Next: fill model API keys, then run scripts/windows/check.ps1"


