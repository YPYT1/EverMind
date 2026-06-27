param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path,
  [string]$EverMindHome = "D:\EverMindMemory",
  [string]$UserHome = $HOME,
  [string]$LlmApiKey = "",
  [string]$MultimodalApiKey = "",
  [string]$EmbeddingApiKey = "",
  [string]$RerankApiKey = "",
  [switch]$NonInteractive,
  [switch]$CopySkillsInsteadOfSymlink,
  [switch]$RunChecks
)

$ErrorActionPreference = "Stop"

function Info($msg) { Write-Host "[EverMind] $msg" -ForegroundColor Cyan }

function Set-EnvLine {
  param(
    [string]$EnvPath,
    [string]$Name,
    [string]$Value
  )
  if ([string]::IsNullOrWhiteSpace($Value)) { return }
  $text = Get-Content -LiteralPath $EnvPath -Raw
  if ($text -match "(?m)^$Name=.*$") {
    $text = $text -replace "(?m)^$Name=.*$", "$Name=$Value"
  } else {
    $text = $text.TrimEnd() + "`n$Name=$Value`n"
  }
  Set-Content -LiteralPath $EnvPath -Value $text -Encoding UTF8
}

if (-not $NonInteractive) {
  $homeInput = Read-Host "EverMind runtime directory [$EverMindHome]"
  if (-not [string]::IsNullOrWhiteSpace($homeInput)) { $EverMindHome = $homeInput }

  $LlmApiKey = Read-Host "LLM API key (blank to skip)"
  $MultimodalApiKey = Read-Host "Multimodal API key (blank to skip)"
  $EmbeddingApiKey = Read-Host "Embedding API key (blank to skip)"
  $RerankApiKey = Read-Host "Rerank API key (blank to skip)"
}

Info "Preparing local runtime and generated MCP config."
& (Join-Path $PSScriptRoot "install-all.ps1") -ProjectRoot $ProjectRoot -EverMindHome $EverMindHome -SkipToolInstall

$envPath = Join-Path $ProjectRoot ".env"
Set-EnvLine -EnvPath $envPath -Name "EVEROS_LLM__API_KEY" -Value $LlmApiKey
Set-EnvLine -EnvPath $envPath -Name "EVEROS_MULTIMODAL__API_KEY" -Value $MultimodalApiKey
Set-EnvLine -EnvPath $envPath -Name "EVEROS_EMBEDDING__API_KEY" -Value $EmbeddingApiKey
Set-EnvLine -EnvPath $envPath -Name "EVEROS_RERANK__API_KEY" -Value $RerankApiKey

Info "Installing EverMind skills into user skill folders."
& (Join-Path $PSScriptRoot "setup-user.ps1") -ProjectRoot $ProjectRoot -UserHome $UserHome -CopyInsteadOfSymlink:$CopySkillsInsteadOfSymlink

if ($RunChecks) {
  Info "Running full stack checks."
  & (Join-Path $PSScriptRoot "check-all.ps1") -ProjectRoot $ProjectRoot
}

Info "Configuration complete."
Info "Generated MCP config: $(Join-Path $ProjectRoot 'generated\mcp-config')"
Info "No existing Codex, Claude Code, Cursor, or Devin config was overwritten."
