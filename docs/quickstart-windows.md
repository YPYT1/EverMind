# Quickstart: Windows

This guide sets up EverMind on Windows for a non-expert user.

## Requirements

- Windows 10 or newer.
- PowerShell 5.1 or newer.
- Git.
- Python 3.11 or newer.
- `uv`.
- Network access for first-time dependency installation.

Check the basics:

```powershell
git --version
python --version
uv --version
```

## 1. Clone

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
```

## 2. Run Guided Setup

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\configure.ps1
```

The guided setup:

- creates local runtime folders;
- creates `.env`;
- renders MCP snippets into `generated\mcp-config`;
- installs or links EverMind skills into user skill folders;
- never overwrites existing Codex, Claude Code, Cursor, or Devin config.

For a complete bootstrap with checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1
```

If the external engines are already installed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\install-all.ps1 -SkipToolInstall
```

## 3. Fill Model Keys

Open `.env` and fill the model API keys:

```powershell
notepad .env
```

At minimum, configure the models your runtime requires. Keep keys local and never commit `.env`.

## 4. Check The Stack

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\check-all.ps1
```

Successful checks should confirm:

- `.env` exists;
- `uv` is available;
- MCP bridge exists;
- skills and templates exist;
- runtime health endpoint responds, if started;
- EverMind Archive Engine is available;
- EverMind Code Graph Engine is available;
- generated MCP snippets exist.

## 5. Copy MCP Config

Use the generated snippet for your client:

```text
generated\mcp-config\codex.toml
generated\mcp-config\claude-code.json
generated\mcp-config\cursor.json
generated\mcp-config\devin.json
```

Do not point the MCP command to an extra nested child directory. EverMind MCP lives directly under `mcp\`.

## 6. Start Runtime

For a terminal run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\start-everos.ps1
```

For a Windows service, use NSSM:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\install-everos-nssm.ps1 -NssmPath C:\path\to\nssm.exe -StartNow
```

MCP is normally started by the agent client. Manual startup is only for testing:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\start-mcp.ps1
```

## Default Paths

```text
<EVERMIND_ROOT>          = D:\Project\EverMind
<EVEROS_ROOT>            = D:\EverMindMemory\everos
<EVERMIND_ARCHIVE_ROOT>  = D:\EverMindMemory\evermind-archive
<CODEX_CONFIG_TOML>      = %USERPROFILE%\.codex\config.toml
```

`<EVEROS_ROOT>` is runtime data. It is not the EverMind repository and not a source checkout.

