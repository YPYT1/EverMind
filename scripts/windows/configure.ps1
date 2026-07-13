param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path,
  [string]$EverMindHome = "D:\EverMindMemory",
  [string]$UserHome = $HOME,
  [string]$SiliconFlowApiKey = "",
  [switch]$NonInteractive,
  [switch]$CopySkillsInsteadOfSymlink,
  [switch]$SkipToolchainInstall,
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
  if ($text -match "(?m)^#?\s*$Name=.*$") {
    $text = $text -replace "(?m)^#?\s*$Name=.*$", "$Name=$Value"
  } else {
    $text = $text.TrimEnd() + "`n$Name=$Value`n"
  }
  Set-Content -LiteralPath $EnvPath -Value $text -Encoding UTF8
}

if (-not $NonInteractive) {
  $homeInput = Read-Host "EverMind runtime directory [$EverMindHome]"
  if (-not [string]::IsNullOrWhiteSpace($homeInput)) { $EverMindHome = $homeInput }

  $SiliconFlowApiKey = Read-Host "SiliconFlow API key (blank to use local models only)"
}

Info "Preparing local runtime and generated MCP config."
& (Join-Path $PSScriptRoot "install-all.ps1") -ProjectRoot $ProjectRoot -EverMindHome $EverMindHome -SkipToolchainInstall:$SkipToolchainInstall

$envPath = Join-Path $ProjectRoot ".env"
Set-EnvLine -EnvPath $envPath -Name "EVERMIND_SILICONFLOW_API_KEY" -Value $SiliconFlowApiKey

Info "Installing EverMind skills into user skill folders."
& (Join-Path $PSScriptRoot "setup-user.ps1") -ProjectRoot $ProjectRoot -UserHome $UserHome -CopyInsteadOfSymlink:$CopySkillsInsteadOfSymlink

if ($RunChecks) {
  Info "Running full stack checks."
  & (Join-Path $PSScriptRoot "check-all.ps1") -ProjectRoot $ProjectRoot
}

Info "Configuration complete."
Info "Generated MCP config: $(Join-Path $ProjectRoot 'generated\mcp-config')"
Info "No existing Codex, Claude Code, Cursor, or Devin config was overwritten."
