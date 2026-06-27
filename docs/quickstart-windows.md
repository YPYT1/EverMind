# Quickstart: Windows

```powershell
git clone https://github.com/your-org/EverMind.git
cd EverMind
powershell -ExecutionPolicy Bypass -File scripts/windows/install.ps1
notepad .env
powershell -ExecutionPolicy Bypass -File scripts/windows/check.ps1
```

Copy a template from `templates/mcp-config/` into your tool configuration.

Use `agents/codex/AGENTS.md`, `agents/claude-code/CLAUDE.md`, `agents/cursor/rules.md`, or `agents/devin/instructions.md` as the matching agent instruction file.

## Placeholder Values

Use these defaults unless you chose custom paths:

```text
<EVERMIND_ROOT>       = D:\Project\EverMind
<EVEROS_ROOT>         = D:\EverMindMemory\everos
<BASIC_MEMORY_ROOT>   = D:\EverMindMemory\basic-memory
<CODEX_CONFIG_TOML>   = %USERPROFILE%\.codex\config.toml
```

`<EVEROS_ROOT>` is the EverOS runtime data directory. It is not the EverMind repository and not the EverOS source checkout.
