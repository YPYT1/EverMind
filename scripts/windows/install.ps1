param(
  [string]$EverMindHome = "D:\EverMindMemory",
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
)

$ErrorActionPreference = "Stop"

$everosRoot = Join-Path $EverMindHome "everos"
$basicRoot = Join-Path $EverMindHome "basic-memory"
$candidateDir = Join-Path $basicRoot ".candidates"

New-Item -ItemType Directory -Force -Path $everosRoot, $basicRoot, $candidateDir | Out-Null

$envPath = Join-Path $ProjectRoot ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
  Copy-Item -LiteralPath (Join-Path $ProjectRoot ".env.example") -Destination $envPath
  (Get-Content -LiteralPath $envPath -Raw).
    Replace("EVERMIND_HOME=", "EVERMIND_HOME=$EverMindHome").
    Replace("EVEROS_ROOT=", "EVEROS_ROOT=$everosRoot").
    Replace("BASIC_MEMORY_ROOT=", "BASIC_MEMORY_ROOT=$basicRoot").
    Replace("BASIC_MEMORY_CANDIDATE_DIR=", "BASIC_MEMORY_CANDIDATE_DIR=$candidateDir") |
    Set-Content -LiteralPath $envPath -Encoding UTF8
}

Write-Host "EverMind local directories are ready."
Write-Host "Env file: $envPath"
Write-Host "Next: fill model API keys, then run scripts/windows/check.ps1"

