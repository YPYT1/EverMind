param(
  [switch]$BestEffort
)

$ErrorActionPreference = "Stop"

function Info($msg) { Write-Host "[EverMind] $msg" -ForegroundColor Cyan }
function Pass($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }

function Stop-Or-Warn($msg) {
  if ($BestEffort) {
    Warn $msg
    return
  }
  throw $msg
}

function Command-Exists($name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Native-Command-Exists($name) {
  $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
  return [bool]$cmd
}

function Add-PathIfExists {
  param([string]$Path)
  if ((Test-Path -LiteralPath $Path) -and ($env:PATH -notlike "*$Path*")) {
    $env:PATH = "$Path;$env:PATH"
    Info "Added toolchain path for this process: $Path"
  }
}

function Add-FirstExistingPath {
  param([string[]]$Paths)
  foreach ($path in $Paths) {
    if (Test-Path -LiteralPath $path) {
      Add-PathIfExists $path
      return $true
    }
  }
  return $false
}

function Add-KnownToolchainPaths {
  Add-FirstExistingPath @(
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin",
    "C:\Program Files\WinLibs\mingw64\bin",
    "C:\Program Files\mingw64\bin",
    "C:\mingw64\bin",
    "C:\msys64\mingw64\bin",
    "C:\msys64\ucrt64\bin"
  ) | Out-Null
  Add-PathIfExists "C:\Program Files\LLVM\bin"
  Add-PathIfExists "C:\Program Files\CMake\bin"
  Add-PathIfExists "$env:LOCALAPPDATA\Microsoft\WinGet\Links"
  Add-FirstExistingPath @(
    "C:\Program Files\Git\usr\bin",
    "C:\Program Files (x86)\Git\usr\bin",
    "D:\Develor_TOOl\Git\usr\bin",
    "C:\msys64\usr\bin"
  ) | Out-Null
  Add-FirstExistingPath @(
    "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin",
    "C:\Program Files\Microsoft Visual Studio\18\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin",
    "C:\Program Files (x86)\Microsoft Visual Studio\17\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin",
    "C:\Program Files\Microsoft Visual Studio\17\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin"
  ) | Out-Null
}

function Install-WingetPackage {
  param(
    [string]$Id,
    [string]$Name
  )
  if (-not (Command-Exists winget)) {
    Stop-Or-Warn "winget is required to install $Name automatically. Install $Name manually, then rerun this script."
    return
  }
  Info "Installing $Name via winget package $Id"
  winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) {
    Stop-Or-Warn "winget failed to install $Name ($Id)"
  }
}

Add-KnownToolchainPaths

if (-not (Command-Exists gcc) -or -not (Command-Exists g++)) {
  Install-WingetPackage -Id "BrechtSanders.WinLibs.POSIX.UCRT" -Name "WinLibs GCC/MinGW toolchain"
  Add-KnownToolchainPaths
}
if (-not (Command-Exists make)) {
  Install-WingetPackage -Id "ezwinports.make" -Name "GNU make"
  Add-KnownToolchainPaths
}
if (-not (Command-Exists clang) -and -not (Command-Exists gcc) -and -not (Command-Exists cl)) {
  Install-WingetPackage -Id "LLVM.LLVM" -Name "LLVM clang"
  Add-KnownToolchainPaths
}
if (-not (Native-Command-Exists sh) -or -not (Native-Command-Exists mkdir) -or -not (Native-Command-Exists rm)) {
  Install-WingetPackage -Id "Git.Git" -Name "Git for Windows coreutils"
  Add-KnownToolchainPaths
}
if (-not (Command-Exists cmake)) {
  Install-WingetPackage -Id "Kitware.CMake" -Name "CMake"
  Add-KnownToolchainPaths
}
if (-not (Command-Exists ninja)) {
  Install-WingetPackage -Id "Ninja-build.Ninja" -Name "Ninja"
  Add-KnownToolchainPaths
}

$missing = @()
if (-not (Command-Exists make)) { $missing += "make" }
if (-not (Command-Exists gcc) -or -not (Command-Exists g++)) { $missing += "gcc/g++ (WinLibs or MinGW)" }

if ($missing.Count -gt 0) {
  Stop-Or-Warn "Toolchain commands still missing from PATH: $($missing -join ', '). Restart the shell or add installed tools to PATH."
} elseif (-not (Native-Command-Exists sh) -or -not (Native-Command-Exists mkdir) -or -not (Native-Command-Exists rm)) {
  Stop-Or-Warn "Unix-compatible shell tools are missing from PATH: sh/mkdir/rm. Install Git for Windows or MSYS2, then rerun this script."
} else {
  if (-not (Command-Exists cmake)) { Warn "Optional CMake is missing; current vendored Makefile build does not require it." }
  if (-not (Command-Exists ninja)) { Warn "Optional Ninja is missing; current vendored Makefile build does not require it." }
  Pass "Source-fusion build toolchain is available"
}
