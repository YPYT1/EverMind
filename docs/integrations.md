# Integrations

## Codex

Use `agents/codex/AGENTS.md` for behavior and `templates/mcp-config/codex.*.toml` for MCP configuration.

## Claude Code

Use `agents/claude-code/CLAUDE.md` and `templates/mcp-config/claude-code.*.json`.

## Cursor

Use `agents/cursor/rules.md` and `templates/mcp-config/cursor.*.json`.

## Devin

Use `agents/devin/instructions.md` and `templates/mcp-config/devin.example.json`.

All snippets use candidate-first Basic Memory writes.

## Placeholder Values

All config snippets may contain placeholders. See [Configuration](configuration.md) for the full reference.

- `<EVERMIND_ROOT>`: path to this EverMind checkout.
- `<EVEROS_ROOT>`: EverOS runtime data root for memory, indexes, logs, and runtime config.
- `<BASIC_MEMORY_ROOT>`: reviewed Basic Memory Markdown archive.
- `<CODEX_CONFIG_TOML>`: Codex config file path.
