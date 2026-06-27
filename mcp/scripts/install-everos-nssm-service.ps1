param(
    [string]$ServiceName = "EverOSMemory3378",
    [string]$EverOSRepo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path,
    [string]$Root = (Join-Path $HOME ".evermind\everos"),
    [string]$NssmPath = "",
    [int]$Port = 3378,
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Nssm {
    param(
        [Parameter(Mandatory = $true)]
        [string]$NssmPath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [string]$FailureMessage = "nssm command failed"
    )

    $output = & $NssmPath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        $detail = ($output | Out-String).Trim()
        if (-not $detail) {
            $detail = "exit code $LASTEXITCODE"
        }
        throw "${FailureMessage}: $detail"
    }
    return $output
}

if (-not (Test-IsAdministrator)) {
    throw "NSSM service registration requires an elevated PowerShell session. Re-run this script as Administrator."
}

if (-not $NssmPath) {
    throw "Pass -NssmPath with the path to nssm.exe."
}
if (-not (Test-Path -LiteralPath $NssmPath)) {
    throw "nssm.exe not found: $NssmPath"
}
if (-not (Test-Path -LiteralPath $EverOSRepo)) {
    throw "EverOS repo not found: $EverOSRepo"
}

$startScript = Join-Path $PSScriptRoot "start-everos-3378.ps1"
if (-not (Test-Path -LiteralPath $startScript)) {
    throw "Start script not found: $startScript"
}

New-Item -ItemType Directory -Force -Path $Root | Out-Null
$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    Invoke-Nssm -NssmPath $NssmPath -Arguments @("install", $ServiceName, "powershell.exe") -FailureMessage "nssm install failed" | Out-Null
}

$parameters = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$startScript`"",
    "-EverOSRepo", "`"$EverOSRepo`"",
    "-Root", "`"$Root`"",
    "-Port", "$Port"
) -join " "

Invoke-Nssm -NssmPath $NssmPath -Arguments @("set", $ServiceName, "Application", "powershell.exe") -FailureMessage "nssm set Application failed" | Out-Null
Invoke-Nssm -NssmPath $NssmPath -Arguments @("set", $ServiceName, "AppParameters", $parameters) -FailureMessage "nssm set AppParameters failed" | Out-Null
Invoke-Nssm -NssmPath $NssmPath -Arguments @("set", $ServiceName, "AppDirectory", $EverOSRepo) -FailureMessage "nssm set AppDirectory failed" | Out-Null
Invoke-Nssm -NssmPath $NssmPath -Arguments @("set", $ServiceName, "Start", "SERVICE_AUTO_START") -FailureMessage "nssm set Start failed" | Out-Null
Invoke-Nssm -NssmPath $NssmPath -Arguments @("set", $ServiceName, "AppStdout", (Join-Path $logDir "everos-service.out.log")) -FailureMessage "nssm set AppStdout failed" | Out-Null
Invoke-Nssm -NssmPath $NssmPath -Arguments @("set", $ServiceName, "AppStderr", (Join-Path $logDir "everos-service.err.log")) -FailureMessage "nssm set AppStderr failed" | Out-Null
Invoke-Nssm -NssmPath $NssmPath -Arguments @("set", $ServiceName, "AppRotateFiles", "1") -FailureMessage "nssm set AppRotateFiles failed" | Out-Null
Invoke-Nssm -NssmPath $NssmPath -Arguments @("set", $ServiceName, "AppRotateOnline", "1") -FailureMessage "nssm set AppRotateOnline failed" | Out-Null
Invoke-Nssm -NssmPath $NssmPath -Arguments @("set", $ServiceName, "AppRotateBytes", "10485760") -FailureMessage "nssm set AppRotateBytes failed" | Out-Null
Invoke-Nssm -NssmPath $NssmPath -Arguments @(
    "set",
    $ServiceName,
    "AppEnvironmentExtra",
    "EVEROS_ROOT=$Root",
    "EVEROS_API__HOST=127.0.0.1",
    "EVEROS_API__PORT=$Port"
) -FailureMessage "nssm set AppEnvironmentExtra failed" | Out-Null

if ($StartNow) {
    Invoke-Nssm -NssmPath $NssmPath -Arguments @("start", $ServiceName) -FailureMessage "nssm start failed" | Out-Null
}

Write-Host "Configured NSSM service '$ServiceName' for EverOS on 127.0.0.1:$Port."
Write-Host "Logs: $logDir"

