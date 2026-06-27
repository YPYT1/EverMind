param(
  [string]$EverMindHome = "D:\EverMindMemory",
  [switch]$SkipToolInstall,
  [switch]$CopySkillsInsteadOfSymlink
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path

Write-Host "EverMind bootstrap starts."
& (Join-Path $PSScriptRoot "install-all.ps1") -ProjectRoot $ProjectRoot -EverMindHome $EverMindHome -SkipToolInstall:$SkipToolInstall
& (Join-Path $PSScriptRoot "setup-user.ps1") -ProjectRoot $ProjectRoot -CopyInsteadOfSymlink:$CopySkillsInsteadOfSymlink
& (Join-Path $PSScriptRoot "check-all.ps1") -ProjectRoot $ProjectRoot

