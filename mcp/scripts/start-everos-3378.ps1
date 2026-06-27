param(
    [string]$EverOSRepo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path,
    [string]$Root = (Join-Path $HOME ".evermind\everos"),
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 3378,
    [string]$LogLevel = "info",
    [string]$UvPath = ""
)

$ErrorActionPreference = "Stop"

function Resolve-Uv {
    param([string]$ExplicitPath)

    if ($ExplicitPath -and (Test-Path -LiteralPath $ExplicitPath)) {
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }

    $cmd = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @()
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    throw "uv.exe was not found. Install uv or pass -UvPath."
}

if (-not (Test-Path -LiteralPath $EverOSRepo)) {
    throw "EverOS repo not found: $EverOSRepo"
}

New-Item -ItemType Directory -Force -Path $Root | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null

$uv = Resolve-Uv -ExplicitPath $UvPath
$env:EVEROS_ROOT = $Root
$env:EVEROS_API__HOST = $BindHost
$env:EVEROS_API__PORT = [string]$Port
$env:EVEROS_LOG_LEVEL = $LogLevel.ToUpperInvariant()

Set-Location -LiteralPath $EverOSRepo
& $uv run --python 3.12 --directory $EverOSRepo everos server start `
    --host $BindHost `
    --port $Port `
    --root $Root `
    --log-level $LogLevel

exit $LASTEXITCODE
