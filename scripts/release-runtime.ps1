param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path,
  [string]$CodebaseBinary = "",
  [string]$OutputDirectory = "",
  [string]$Target = ""
)

$ErrorActionPreference = "Stop"

if (-not $CodebaseBinary) {
  & (Join-Path $ProjectRoot "scripts\build-vendored-codebase.ps1") -ProjectRoot $ProjectRoot
  $CodebaseBinary = Join-Path $ProjectRoot "third_party\codebase-memory-mcp\build\c\codebase-memory-mcp.exe"
}
if (-not $OutputDirectory) {
  $OutputDirectory = Join-Path $ProjectRoot "dist\runtime"
}
if (-not (Test-Path -LiteralPath $CodebaseBinary -PathType Leaf)) {
  throw "Codebase engine binary not found: $CodebaseBinary"
}

$arguments = @(
  "run",
  "--frozen",
  "--directory",
  (Join-Path $ProjectRoot "mcp"),
  "python",
  "-m",
  "scripts.release_runtime_bundle",
  "--repo-root",
  $ProjectRoot,
  "--codebase-binary",
  $CodebaseBinary,
  "--output-directory",
  $OutputDirectory
)
if ($Target) {
  $arguments += @("--target", $Target)
}

& uv @arguments
if ($LASTEXITCODE -ne 0) {
  throw "Runtime release failed with exit code $LASTEXITCODE"
}
