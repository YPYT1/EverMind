param(
  [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
)

$ErrorActionPreference = "Stop"
$ok = $true

function Pass($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow; $script:ok = $false }
function Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Add-PathIfExists($path) {
  if ((Test-Path -LiteralPath $path) -and ($env:PATH -notlike "*$path*")) {
    $env:PATH = "$path;$env:PATH"
  }
}

Add-PathIfExists "C:\Program Files\LLVM\bin"
Add-PathIfExists "$env:LOCALAPPDATA\Microsoft\WinGet\Links"
foreach ($path in @(
  "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin",
  "C:\Program Files\WinLibs\mingw64\bin",
  "C:\Program Files\mingw64\bin",
  "C:\mingw64\bin",
  "C:\msys64\mingw64\bin",
  "C:\msys64\ucrt64\bin",
  "C:\Program Files\Git\usr\bin",
  "C:\Program Files (x86)\Git\usr\bin",
  "D:\Develor_TOOl\Git\usr\bin",
  "C:\msys64\usr\bin"
)) {
  Add-PathIfExists $path
}

try {
  & (Join-Path $PSScriptRoot "check.ps1") -ProjectRoot $ProjectRoot
  if (-not $?) { $ok = $false }
} catch {
  Warn "base EverMind checks failed: $($_.Exception.Message)"
}

$envPath = Join-Path $ProjectRoot ".env"
$envText = ""
if (Test-Path -LiteralPath $envPath) {
  $envText = Get-Content -LiteralPath $envPath -Raw
}

Pass "Built-in EverMind Archive engine available"
Pass "Built-in EverMind Code Graph engine available"

$missingToolchain = @()
if (-not (Get-Command make -ErrorAction SilentlyContinue)) { $missingToolchain += "make" }
if (-not (Get-Command gcc -ErrorAction SilentlyContinue) -or -not (Get-Command g++ -ErrorAction SilentlyContinue)) { $missingToolchain += "gcc/g++ (WinLibs or MinGW)" }
if (
  -not (Get-Command sh -CommandType Application -ErrorAction SilentlyContinue) -or
  -not (Get-Command mkdir -CommandType Application -ErrorAction SilentlyContinue) -or
  -not (Get-Command rm -CommandType Application -ErrorAction SilentlyContinue)
) { $missingToolchain += "git/msys coreutils" }
if ($missingToolchain.Count -eq 0) {
  Pass "Source-fusion C build toolchain available"
} else {
  Info "Source-fusion build toolchain incomplete: $($missingToolchain -join ', '). Run scripts\windows\install-toolchain.ps1"
}
if (Get-Command cmake -ErrorAction SilentlyContinue) {
  Pass "Optional CMake available"
} else {
  Info "Optional CMake not found; current vendored Makefile build does not require it"
}
if (Get-Command ninja -ErrorAction SilentlyContinue) {
  Pass "Optional Ninja available"
} else {
  Info "Optional Ninja not found; current vendored Makefile build does not require it"
}

$bmSource = Join-Path $ProjectRoot "third_party\basic-memory"
if (
  (Test-Path -LiteralPath (Join-Path $bmSource "LICENSE")) -and
  (Select-String -LiteralPath (Join-Path $bmSource "pyproject.toml") -Pattern "AGPL-3.0-or-later" -Quiet) -and
  (Test-Path -LiteralPath (Join-Path $bmSource "src\basic_memory\mcp")) -and
  (Test-Path -LiteralPath (Join-Path $bmSource "src\basic_memory\markdown\entity_parser.py"))
) {
  Pass "Source-fused Basic Memory source integrated"
} else {
  Warn "Source-fused Basic Memory source incomplete"
}

$cbmSource = Join-Path $ProjectRoot "third_party\codebase-memory-mcp"
$cbmBinaryExe = Join-Path $cbmSource "build\c\codebase-memory-mcp.exe"
$cbmBinaryBare = Join-Path $cbmSource "build\c\codebase-memory-mcp"
if (Test-Path -LiteralPath (Join-Path $cbmSource "internal\cbm\vendored\grammars\lean\parser.c.chunks\parser.c.sha256")) {
  try {
    & (Join-Path $ProjectRoot "scripts\restore-vendored-codebase.ps1") -ProjectRoot $ProjectRoot
  } catch {
    Warn "Vendored codebase chunk restore failed: $($_.Exception.Message)"
  }
}
$grammarDir = Join-Path $cbmSource "internal\cbm\vendored\grammars"
$lspDir = Join-Path $cbmSource "internal\cbm\lsp"
$requiredLsp = @(
  "py_lsp.c",
  "ts_lsp.c",
  "php_lsp.c",
  "cs_lsp.c",
  "go_lsp.c",
  "c_lsp.c",
  "java_lsp.c",
  "kotlin_lsp.c",
  "rust_lsp.c"
)
$grammarCount = 0
if (Test-Path -LiteralPath $grammarDir) {
  $grammarCount = @(Get-ChildItem -LiteralPath $grammarDir -Directory -ErrorAction SilentlyContinue).Count
}
$missingLsp = @($requiredLsp | Where-Object { -not (Test-Path -LiteralPath (Join-Path $lspDir $_)) })
if (
  (Test-Path -LiteralPath (Join-Path $cbmSource "Makefile.cbm")) -and
  (Test-Path -LiteralPath (Join-Path $cbmSource "internal\cbm\lsp_all.c")) -and
  (Test-Path -LiteralPath (Join-Path $grammarDir "MANIFEST.md")) -and
  (Test-Path -LiteralPath (Join-Path $grammarDir "lean\parser.c")) -and
  (Test-Path -LiteralPath (Join-Path $cbmSource "vendored\zlib\zlib.h")) -and
  (Test-Path -LiteralPath (Join-Path $cbmSource "vendored\zlib\inflate.c")) -and
  (Test-Path -LiteralPath (Join-Path $cbmSource "vendored\zlib\LICENSE")) -and
  $grammarCount -ge 159 -and
  $missingLsp.Count -eq 0
) {
  Pass "Vendored codebase-memory-mcp source integrated"
} else {
  Warn "Vendored codebase-memory-mcp source incomplete"
}
if ((Test-Path -LiteralPath $cbmBinaryExe) -or (Test-Path -LiteralPath $cbmBinaryBare)) {
  Pass "Vendored codebase-memory-mcp binary built"
} else {
  Info "Vendored codebase-memory-mcp binary not built; native Python code graph fallback remains active"
}

if ($envText -match "(?m)^EVERMIND_ARCHIVE_CANDIDATE_DIR=(.+)$") {
  $candidateDir = $Matches[1].Trim()
  if ($candidateDir -and (Test-Path -LiteralPath $candidateDir)) { Pass "EverMind Archive candidate dir exists" } else { Warn "EverMind Archive candidate dir missing" }
} else {
  Warn "EVERMIND_ARCHIVE_CANDIDATE_DIR missing from .env"
}

$modelVars = @(
  "EVEROS_LLM__API_KEY",
  "EVEROS_MULTIMODAL__API_KEY",
  "EVEROS_EMBEDDING__API_KEY",
  "EVEROS_RERANK__API_KEY"
)
foreach ($name in $modelVars) {
  if ($envText -match "(?m)^$name=.+$") { Pass "$name is set" } else { Info "$name is empty; model-backed features remain optional" }
}

if (Test-Path -LiteralPath (Join-Path $ProjectRoot "generated\mcp-config\codex.toml")) {
  Pass "generated MCP snippets exist"
} else {
  Warn "generated MCP snippets missing; run install-all"
}

if (-not $ok) { exit 1 }
Pass "EverMind full stack checks passed"

