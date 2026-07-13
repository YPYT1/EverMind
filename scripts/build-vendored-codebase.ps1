param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
  [switch]$BestEffort
)

$ErrorActionPreference = "Stop"

function Info($msg) { Write-Host "[EverMind] $msg" -ForegroundColor Cyan }
function Pass($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

function Stop-Or-Warn($msg) {
  if ($BestEffort) {
    Warn $msg
    exit 0
  }
  throw $msg
}

function Add-PathIfExists {
  param([string]$Path)
  if ((Test-Path -LiteralPath $Path) -and ($env:PATH -notlike "*$Path*")) {
    $env:PATH = "$Path;$env:PATH"
  }
}

function Add-FirstExistingPath {
  param([string[]]$Paths)
  foreach ($path in $Paths) {
    if (Test-Path -LiteralPath $path) {
      Add-PathIfExists $path
      return $path
    }
  }
  return $null
}

Add-FirstExistingPath @(
  "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin",
  "C:\Program Files\WinLibs\mingw64\bin",
  "C:\Program Files\mingw64\bin",
  "C:\mingw64\bin",
  "C:\msys64\mingw64\bin",
  "C:\msys64\ucrt64\bin"
) | Out-Null
Add-PathIfExists "C:\Program Files\LLVM\bin"
Add-PathIfExists "$env:LOCALAPPDATA\Microsoft\WinGet\Links"
Add-FirstExistingPath @(
  "C:\Program Files\Git\usr\bin",
  "C:\Program Files (x86)\Git\usr\bin",
  "D:\Develor_TOOl\Git\usr\bin",
  "C:\msys64\usr\bin"
) | Out-Null

$source = Join-Path $ProjectRoot "third_party\codebase-memory-mcp"
$makefile = Join-Path $source "Makefile.cbm"
$binary = Join-Path $source "build\c\codebase-memory-mcp.exe"
$bareBinary = Join-Path $source "build\c\codebase-memory-mcp"

if (-not (Test-Path -LiteralPath $makefile)) {
  Stop-Or-Warn "Vendored codebase-memory-mcp source is missing: $source"
}

& (Join-Path $ProjectRoot "scripts\restore-vendored-codebase.ps1") -ProjectRoot $ProjectRoot

if ((Test-Path -LiteralPath $binary) -or (Test-Path -LiteralPath $bareBinary)) {
  Pass "Vendored codebase-memory-mcp binary already built"
  exit 0
}

$make = Get-Command make -ErrorAction SilentlyContinue
$compiler = Get-Command gcc,clang,cc -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $make -or -not $compiler) {
  Stop-Or-Warn "C toolchain not found. Install make plus clang/gcc, then rerun scripts/build-vendored-codebase.ps1."
}
if (
  -not (Get-Command sh -CommandType Application -ErrorAction SilentlyContinue) -or
  -not (Get-Command mkdir -CommandType Application -ErrorAction SilentlyContinue) -or
  -not (Get-Command rm -CommandType Application -ErrorAction SilentlyContinue)
) {
  Stop-Or-Warn "Unix-compatible shell tools not found. Install Git for Windows/MSYS2, then rerun scripts/build-vendored-codebase.ps1."
}

Info "Building vendored codebase-memory-mcp from source"
Push-Location $source
try {
  $makeArgs = @("-f", "Makefile.cbm")
  $makeArgs += "SHELL=sh.exe"
  if ($compiler.Name -like "gcc*") {
    $makeArgs += "CC=gcc"
    if (Get-Command g++ -ErrorAction SilentlyContinue) {
      $makeArgs += "CXX=g++"
    }
  } elseif ($compiler.Name -like "clang*") {
    $makeArgs += "CC=clang"
    if (Get-Command clang++ -ErrorAction SilentlyContinue) {
      $makeArgs += "CXX=clang++"
    }
  }
  $makeArgs += "cbm"
  & $make.Source @makeArgs
  if ($LASTEXITCODE -ne 0) {
    Stop-Or-Warn "Vendored codebase-memory-mcp build failed with exit code $LASTEXITCODE"
  }
} finally {
  Pop-Location
}

if ((Test-Path -LiteralPath $binary) -or (Test-Path -LiteralPath $bareBinary)) {
  Pass "Vendored codebase-memory-mcp built successfully"
} else {
  Stop-Or-Warn "Build completed but binary was not found under third_party\codebase-memory-mcp\build\c"
}
