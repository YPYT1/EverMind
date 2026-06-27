param(
  [string]$ServiceName = "EverMindEverOS3378",
  [string]$EverOSRepo = "",
  [string]$EverOSRoot = "D:\EverMindMemory\everos",
  [string]$NssmPath,
  [int]$Port = 3378,
  [switch]$StartNow
)

$ErrorActionPreference = "Stop"

if (-not $NssmPath) {
  throw "Pass -NssmPath with the path to nssm.exe."
}
if (-not (Test-Path -LiteralPath $NssmPath)) {
  throw "nssm.exe not found: $NssmPath"
}

$startScript = Join-Path $PSScriptRoot "start-everos.ps1"
$args = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$startScript`"",
  "-EverOSRoot", "`"$EverOSRoot`"",
  "-Port", "$Port"
)
if ($EverOSRepo) {
  $args += @("-EverOSRepo", "`"$EverOSRepo`"")
}
$parameters = $args -join " "

New-Item -ItemType Directory -Force -Path (Join-Path $EverOSRoot "logs") | Out-Null

& $NssmPath install $ServiceName powershell.exe | Out-Null
& $NssmPath set $ServiceName Application powershell.exe | Out-Null
& $NssmPath set $ServiceName AppParameters $parameters | Out-Null
& $NssmPath set $ServiceName AppStdout (Join-Path $EverOSRoot "logs\everos-service.out.log") | Out-Null
& $NssmPath set $ServiceName AppStderr (Join-Path $EverOSRoot "logs\everos-service.err.log") | Out-Null
& $NssmPath set $ServiceName Start SERVICE_AUTO_START | Out-Null

if ($StartNow) {
  & $NssmPath start $ServiceName | Out-Null
}

Write-Host "Configured NSSM service $ServiceName for EverOS on 127.0.0.1:$Port"

