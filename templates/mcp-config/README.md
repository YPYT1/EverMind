# MCP Config Templates

These files are copy/paste templates for MCP clients.

Before using any template, replace the placeholders documented in [Configuration](../../docs/configuration.md):

- `<EVERMIND_ROOT>`
- `<EVEROS_ROOT>`
- `<BASIC_MEMORY_ROOT>`
- `<EVEROS_REPO>`
- `<CODEX_CONFIG_TOML>`

## What `EVEROS_ROOT` Means

`EVEROS_ROOT` is the EverOS runtime data directory. It stores local memory files, indexes, logs, and runtime config.

It is not the EverMind repository path and not the EverOS source-code path.

Examples:

- Windows: `D:\EverMindMemory\everos`
- macOS: `$HOME/.evermind/everos`

## What `BASIC_MEMORY_ROOT` Means

`BASIC_MEMORY_ROOT` is the reviewed Markdown project archive.

Examples:

- Windows: `D:\EverMindMemory\basic-memory`
- macOS: `$HOME/BasicMemory`

