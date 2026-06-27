# User Journey

This is the intended non-expert setup flow.

## 1. Download EverMind

```bash
git clone https://github.com/<org>/EverMind.git
cd EverMind
```

## 2. Run Bootstrap

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/bootstrap.ps1
```

macOS:

```bash
bash scripts/macos/bootstrap.sh
```

Bootstrap:

1. creates local runtime folders;
2. creates `.env` from `.env.example`;
3. installs or checks Basic Memory and codebase-memory-mcp;
4. generates MCP snippets in `generated/mcp-config/`;
5. links EverMind skills into user skill folders;
6. runs environment and connectivity checks.

It does not overwrite existing Codex, Claude Code, Cursor, or Devin configs.

If you prefer a guided setup, run the configure script instead:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/configure.ps1
```

```bash
bash scripts/macos/configure.sh
```

Configure asks for the memory folder and model keys, then creates `.env`, generated MCP snippets, and user skill links. For unattended setup, use `-NonInteractive` on Windows or `NON_INTERACTIVE=1` on macOS.

## 3. Fill Model Keys

Open `.env` and fill the model API keys.

`.env.example` is the runtime environment template. It exists because secrets and machine-specific paths should not live in the readable system config.

`config/evermind.example.yaml` is the one-file human-readable system configuration reference.

## 4. Copy One MCP Config

Use the generated file for your tool:

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

Do not paste configs that point to an extra nested MCP child directory. EverMind ships the MCP bridge directly under `mcp/`.

## 5. Start EverOS

Terminal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/start-everos.ps1
```

```bash
bash scripts/macos/start-everos.sh
```

Windows service with NSSM:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/install-everos-nssm.ps1 -NssmPath C:\path\to\nssm.exe -StartNow
```

MCP itself is usually started by the client from MCP config. Manual MCP startup is only for testing.

Manual MCP startup:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/start-mcp.ps1
```

```bash
bash scripts/macos/start-mcp.sh
```

## Skill Install Locations

EverMind installs skills for the user, not just for this repository:

```text
~/.agents/skills
~/.codex/skills    when ~/.codex exists
~/.claude/skills   when ~/.claude exists
```

The setup script links by default and copies when linking is not possible.

## 6. Use It

Ask the agent:

```text
Use EverMind. Start with briefing for this project, then recall known pitfalls.
```

At the end of meaningful work, the agent should create a Basic Memory candidate, not silently write official notes.
