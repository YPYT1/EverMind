# EverMind v2 Setup Script - Windows
# Detects your environment and installs everything needed.
# Usage: Right-click > Run with PowerShell
#   Or:  powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

function Write-Header($msg) {
    $sep = "=" * 60
    Write-Host ""
    Write-Host $sep -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host $sep -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "  [OK]  $msg" -ForegroundColor Green
}

function Write-WARN($msg) {
    Write-Host "  [WARN] $msg" -ForegroundColor Yellow
}

function Write-FAIL($msg) {
    Write-Host "  [FAIL] $msg" -ForegroundColor Red
    exit 1
}

function Write-Step($msg) {
    Write-Host "  -->  $msg"
}

# ---------------------------------------------------------------------------
# SECTION 1: Environment Detection
# ---------------------------------------------------------------------------

Write-Header "EverMind v2 - Environment Detection"

# a) Python check
$PythonCmd = $null
$pythonVersion = $null

try {
    $pythonVersion = & python --version 2>&1
    $PythonCmd = "python"
} catch {
    try {
        $pythonVersion = & py --version 2>&1
        $PythonCmd = "py"
    } catch {
        # neither found
    }
}

if ($null -eq $PythonCmd) {
    Write-FAIL "Python not found. Install Python 3.11+ from https://python.org and re-run."
} else {
    # Parse version string like "Python 3.11.4"
    if ($pythonVersion -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) {
            Write-OK "Python $major.$minor found ($PythonCmd)"
        } else {
            Write-FAIL "Python $major.$minor is too old. EverMind requires Python 3.11+."
        }
    } else {
        Write-FAIL "Could not parse Python version from: $pythonVersion"
    }
}

# b) uv check
$uvFound = $false
try {
    $uvVer = & uv --version 2>&1
    Write-OK "uv found: $uvVer"
    $uvFound = $true
} catch {
    Write-WARN "uv not found."
    $answer = Read-Host "  Install uv now? (Y/n)"
    if ($answer -eq "" -or $answer -match "^[Yy]") {
        Write-Step "Installing uv via official installer..."
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        # Refresh PATH in this session
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "User") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
        try {
            $uvVer = & uv --version 2>&1
            Write-OK "uv installed: $uvVer"
            $uvFound = $true
        } catch {
            Write-FAIL "uv installation failed or is not on PATH. Please restart your shell and re-run."
        }
    } else {
        Write-FAIL "uv is required. Install it from https://github.com/astral-sh/uv and re-run."
    }
}

# c) git check
try {
    $gitVer = & git --version 2>&1
    Write-OK "git found: $gitVer"
} catch {
    Write-WARN "git not found. Git is optional but recommended for updates."
}

# d) sentence-transformers check
$stResult = & $PythonCmd -c "import sentence_transformers; print('ok')" 2>$null
if ($stResult -eq "ok") {
    Write-OK "sentence-transformers available"
} else {
    Write-WARN "sentence-transformers not found. Install with: uv pip install sentence-transformers"
}

# e) sqlite-vec check
$svResult = & $PythonCmd -c "import sqlite_vec; print('ok')" 2>$null
if ($svResult -eq "ok") {
    Write-OK "sqlite-vec available"
} else {
    Write-WARN "sqlite-vec not found. Install with: uv pip install sqlite-vec"
}

# ---------------------------------------------------------------------------
# SECTION 2: Install EverMind
# ---------------------------------------------------------------------------

Write-Header "Installing EverMind MCP Server"

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$EverMindRoot = Split-Path -Parent $ScriptDir          # project root (one level above scripts/)
$McpDir       = Join-Path $EverMindRoot "mcp"

if (-not (Test-Path $McpDir)) {
    Write-FAIL "mcp directory not found at: $McpDir"
}

Write-Step "Installing EverMind + all dependencies (sqlite-vec, sentence-transformers)..."
& uv sync --directory $McpDir --extra full
if ($LASTEXITCODE -ne 0) {
    Write-FAIL "uv sync failed."
}

Write-Step "Smoke-testing EverMind import..."
$smokeResult = & uv run --directory $McpDir $PythonCmd -c "from evermind_mcp.config_v2 import load_config; from evermind_mcp.storage import EmbeddedStorage; import pathlib, tempfile; tmp=tempfile.mkdtemp(); cfg=load_config(); s=EmbeddedStorage(pathlib.Path(tmp)/'test.db'); s.close_all(); print('ok')" 2>&1
if ($smokeResult -match "ok") {
    Write-OK "EverMind MCP server installed and importable."
} else {
    Write-FAIL "Smoke test failed. Output: $smokeResult"
}

# ---------------------------------------------------------------------------
# SECTION 3: Install integrated engines
# ---------------------------------------------------------------------------

Write-Header "Installing Integrated Code Graph and Archive Engines"

& (Join-Path $EverMindRoot "scripts\windows\install-all.ps1") -ProjectRoot $EverMindRoot -EverMindHome "$env:USERPROFILE\.evermind"
if ($LASTEXITCODE -ne 0) {
    Write-FAIL "Integrated engine installation failed."
}
Write-OK "Integrated engines installed. Users still register only the evermind MCP server."

# ---------------------------------------------------------------------------
# SECTION 4: Detect Config Paths
# ---------------------------------------------------------------------------

Write-Header "Detecting Platform Config Paths"

$EverMindRoot = $EverMindRoot -replace '\\', '/'   # already set above; normalize to forward slashes

$ClaudeConfigPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"

# Cursor: prefer AppData path, fall back to USERPROFILE
$CursorConfigPath1 = Join-Path $env:APPDATA "Cursor\User\globalStorage\cursor.mcp\mcp.json"
$CursorConfigPath2 = Join-Path $env:USERPROFILE ".cursor\mcp.json"

if (Test-Path $CursorConfigPath1) {
    $CursorConfigPath = $CursorConfigPath1
} else {
    $CursorConfigPath = $CursorConfigPath2
}

Write-Step "Claude Desktop config: $ClaudeConfigPath"
Write-Step "Cursor config:         $CursorConfigPath"

$McpEntry = @{
    command = "uv"
    args    = @("run", "--directory", "$EverMindRoot/mcp", "evermind-mcp")
}

# ---------------------------------------------------------------------------
# SECTION 5: Configure Claude Desktop and Cursor
# ---------------------------------------------------------------------------

Write-Header "Claude Desktop Configuration"

function Update-McpConfig($ConfigPath, $AppName) {
    $entryJson = $McpEntry | ConvertTo-Json -Depth 5

    if (Test-Path $ConfigPath) {
        $raw = Get-Content $ConfigPath -Raw -Encoding UTF8
        $json = $raw | ConvertFrom-Json

        # Add mcpServers if missing
        if ($null -eq $json.mcpServers) {
            $json | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value ([PSCustomObject]@)
        }

        # Set evermind entry
        $json.mcpServers | Add-Member -MemberType NoteProperty -Name "evermind" -Value $McpEntry -Force

        $json | ConvertTo-Json -Depth 10 | Set-Content $ConfigPath -Encoding UTF8
        Write-OK "Updated $ConfigPath"
        Write-Step "Restart $AppName to apply changes."
    } elseif (Test-Path (Split-Path -Parent $ConfigPath)) {
        # Parent directory exists — create the config file
        $newConfig = [PSCustomObject]@{
            mcpServers = [PSCustomObject]@{
                evermind = $McpEntry
            }
        }
        $newConfig | ConvertTo-Json -Depth 10 | Set-Content $ConfigPath -Encoding UTF8
        Write-OK "Created $ConfigPath"
        Write-Step "Restart $AppName to apply changes."
    } else {
        Write-WARN "$AppName config directory not found. Skipping auto-configuration."
        Write-Step "To configure manually, add the following to your $AppName MCP config:"
        Write-Host ""
        Write-Host '  {' -ForegroundColor White
        Write-Host '    "mcpServers": {' -ForegroundColor White
        Write-Host '      "evermind": ' -ForegroundColor White -NoNewline
        Write-Host ($McpEntry | ConvertTo-Json -Depth 5) -ForegroundColor White
        Write-Host '    }' -ForegroundColor White
        Write-Host '  }' -ForegroundColor White
        Write-Host ""
    }
}

Update-McpConfig -ConfigPath $ClaudeConfigPath -AppName "Claude Desktop"
Update-McpConfig -ConfigPath $CursorConfigPath  -AppName "Cursor"

# ---------------------------------------------------------------------------
# SECTION 6: Memory Directory
# ---------------------------------------------------------------------------

$MemDir = "$env:USERPROFILE\.evermind"
New-Item -ItemType Directory -Force -Path $MemDir | Out-Null
Write-OK "Memory directory ready: $MemDir"

# ---------------------------------------------------------------------------
# SECTION 7: Summary
# ---------------------------------------------------------------------------

Write-Header "Setup Complete"

Write-Host ""
Write-Host "  What was checked and configured:" -ForegroundColor White
Write-Host "    - Python ($PythonCmd): version verified >= 3.11" -ForegroundColor White
Write-Host "    - uv: package manager verified / installed" -ForegroundColor White
Write-Host "    - git: presence checked (optional)" -ForegroundColor White
Write-Host "    - sentence-transformers: availability checked" -ForegroundColor White
Write-Host "    - sqlite-vec: availability checked" -ForegroundColor White
Write-Host "    - EverMind MCP server: dependencies synced and smoke-tested" -ForegroundColor White
Write-Host "    - Integrated engines: code graph and archive installed/configured" -ForegroundColor White
Write-Host "    - Claude Desktop config: $ClaudeConfigPath" -ForegroundColor White
Write-Host "    - Cursor config: $CursorConfigPath" -ForegroundColor White
Write-Host "    - Memory directory: $MemDir" -ForegroundColor White
Write-Host ""
Write-Host "  Step 1 - Restart Claude Desktop or Cursor to apply changes." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Step 2 - Add the EverMind skill to your project:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Add this line to your project's CLAUDE.md or AGENTS.md:" -ForegroundColor White
Write-Host ""
Write-Host "    `$`$EverMindRoot/skills/evermind/SKILL.md" -ForegroundColor Yellow
Write-Host ""
Write-Host "  This tells Claude Code when and how to use EverMind memory." -ForegroundColor White
Write-Host "  Or copy agents/claude-code/CLAUDE.md as a starting template." -ForegroundColor White
Write-Host ""
