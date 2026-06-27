# Quickstart: macOS

```bash
git clone https://github.com/your-org/EverMind.git
cd EverMind
bash scripts/macos/install.sh
$EDITOR .env
bash scripts/macos/check.sh
```

Copy a template from `templates/mcp-config/` into your tool configuration.

Use the matching file under `agents/` for Codex, Claude Code, Cursor, or Devin.

## Placeholder Values

Use these defaults unless you chose custom paths:

```text
<EVERMIND_ROOT>       = $HOME/EverMind
<EVEROS_ROOT>         = $HOME/.evermind/everos
<BASIC_MEMORY_ROOT>   = $HOME/BasicMemory
<CODEX_CONFIG_TOML>   = $HOME/.codex/config.toml
```

`<EVEROS_ROOT>` is the EverOS runtime data directory. It is not the EverMind repository and not the EverOS source checkout.
