param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

function Info($msg) { Write-Host "[EverMind] $msg" -ForegroundColor Cyan }
function Pass($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Get-Sha256Hex($path) {
  $cmd = Get-Command Get-FileHash -ErrorAction SilentlyContinue
  if ($cmd) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  }

  $sha = [System.Security.Cryptography.SHA256]::Create()
  $stream = [System.IO.File]::OpenRead($path)
  try {
    $hash = $sha.ComputeHash($stream)
    return ([System.BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
  } finally {
    $stream.Dispose()
    $sha.Dispose()
  }
}

$leanDir = Join-Path $ProjectRoot "third_party\codebase-memory-mcp\internal\cbm\vendored\grammars\lean"
$target = Join-Path $leanDir "parser.c"
$chunksDir = Join-Path $leanDir "parser.c.chunks"
$shaFile = Join-Path $chunksDir "parser.c.sha256"
$sizeFile = Join-Path $chunksDir "parser.c.size"

if (-not (Test-Path -LiteralPath $shaFile)) {
  throw "Vendored codebase chunks are missing: $shaFile"
}

$expectedHash = ((Get-Content -LiteralPath $shaFile -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
$expectedSize = [int64](Get-Content -LiteralPath $sizeFile -Raw).Trim()

if (Test-Path -LiteralPath $target) {
  $actual = Get-Item -LiteralPath $target
  $actualHash = Get-Sha256Hex $target
  if ($actual.Length -eq $expectedSize -and $actualHash -eq $expectedHash) {
    Pass "Vendored codebase lean parser already restored"
    exit 0
  }
  Remove-Item -LiteralPath $target -Force
}

Info "Restoring vendored codebase lean parser from repository chunks"
$tmp = "$target.tmp"
if (Test-Path -LiteralPath $tmp) {
  Remove-Item -LiteralPath $tmp -Force
}

$out = [System.IO.File]::Create($tmp)
try {
  foreach ($part in Get-ChildItem -LiteralPath $chunksDir -Filter "parser.c.part*" | Sort-Object Name) {
    $bytes = [System.IO.File]::ReadAllBytes($part.FullName)
    $out.Write($bytes, 0, $bytes.Length)
  }
} finally {
  $out.Dispose()
}

$restored = Get-Item -LiteralPath $tmp
$restoredHash = Get-Sha256Hex $tmp
if ($restored.Length -ne $expectedSize -or $restoredHash -ne $expectedHash) {
  Remove-Item -LiteralPath $tmp -Force
  throw "Restored lean parser failed checksum validation"
}

Move-Item -LiteralPath $tmp -Destination $target -Force
Pass "Vendored codebase lean parser restored"
