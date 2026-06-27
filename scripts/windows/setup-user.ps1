param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path,
  [string]$UserHome = $HOME,
  [switch]$CopyInsteadOfSymlink
)

$ErrorActionPreference = "Stop"

function Info($msg) { Write-Host "[EverMind] $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

function Link-Or-Copy {
  param(
    [string]$Source,
    [string]$Destination
  )
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
  if (Test-Path -LiteralPath $Destination) {
    Info "Already exists: $Destination"
    return
  }
  if ($CopyInsteadOfSymlink) {
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse
    Info "Copied: $Destination"
    return
  }
  try {
    New-Item -ItemType SymbolicLink -Path $Destination -Target $Source | Out-Null
    Info "Linked: $Destination -> $Source"
  } catch {
    Warn "Symlink failed, copying instead: $($_.Exception.Message)"
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse
  }
}

$sourceSkills = Join-Path $ProjectRoot "skills"
$agentsSkills = Join-Path $UserHome ".agents\skills"
New-Item -ItemType Directory -Force -Path $agentsSkills | Out-Null

Get-ChildItem -LiteralPath $sourceSkills -Directory | ForEach-Object {
  Link-Or-Copy -Source $_.FullName -Destination (Join-Path $agentsSkills $_.Name)
}

$clientSkillRoots = @(
  (Join-Path $UserHome ".codex\skills"),
  (Join-Path $UserHome ".claude\skills")
)

foreach ($clientSkills in $clientSkillRoots) {
  $clientHome = Split-Path -Parent $clientSkills
  if (-not (Test-Path -LiteralPath $clientHome)) {
    Warn "Client directory not found, skipping: $clientHome"
    continue
  }
  New-Item -ItemType Directory -Force -Path $clientSkills | Out-Null
  Get-ChildItem -LiteralPath $sourceSkills -Directory | ForEach-Object {
    $agentSkill = Join-Path $agentsSkills $_.Name
    Link-Or-Copy -Source $agentSkill -Destination (Join-Path $clientSkills $_.Name)
  }
}

Info "User skills setup complete."

