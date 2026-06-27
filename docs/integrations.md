# Integrations

EverMind supports agents through two files:

1. an instruction file that teaches the agent how to use memory;
2. an MCP snippet that starts `evermind-mcp`.

Setup scripts render ready-to-copy snippets into `generated/mcp-config/`.

## Codex

Use:

- behavior: `agents/codex/AGENTS.md`;
- generated MCP config: `generated/mcp-config/codex.toml`;
- template: `templates/mcp-config/codex.windows.toml` or `templates/mcp-config/codex.macos.toml`.

The MCP server key is:

```toml
[mcp_servers.evermind]
```

Expected command:

```text
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

## Claude Code

Use:

- behavior: `agents/claude-code/CLAUDE.md`;
- generated MCP config: `generated/mcp-config/claude-code.json`;
- template: `templates/mcp-config/claude-code.windows.json` or `templates/mcp-config/claude-code.macos.json`.

Claude Code should see EverMind as one MCP server named `evermind`.

## Cursor

Use:

- behavior: `agents/cursor/rules.md`;
- generated MCP config: `generated/mcp-config/cursor.json`;
- template: `templates/mcp-config/cursor.windows.json` or `templates/mcp-config/cursor.macos.json`.

Cursor rules should instruct the agent to read memory before substantial code changes and to propose archive updates after meaningful work.

## Devin

Use:

- behavior: `agents/devin/instructions.md`;
- generated MCP config: `generated/mcp-config/devin.json`;
- template: `templates/mcp-config/devin.example.json`.

## Skill Install Locations

User setup scripts install or link EverMind skills into:

```text
~/.agents/skills
~/.codex/skills    when ~/.codex exists
~/.claude/skills   when ~/.claude exists
```

On Windows, `setup-user.ps1` can copy instead of symlink:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\setup-user.ps1 -CopyInsteadOfSymlink
```

## Candidate-First Archive Writes

All agent templates use candidate-first archive writes. The recommended flow is:

1. start work with `briefing`;
2. use `recall` for task-specific context;
3. use `remember` for useful realtime facts;
4. use `propose_basic_memory_update` after meaningful work;
5. use `commit_basic_memory_update` only after explicit user confirmation.

## Placeholder Values

All config snippets may contain placeholders. See [Configuration](configuration.md) for the full reference.

- `<EVERMIND_ROOT>`: path to this EverMind checkout.
- `<EVEROS_ROOT>`: runtime data root for memory, indexes, logs, and runtime config.
- `<EVERMIND_ARCHIVE_ROOT>`: reviewed EverMind Archive Markdown archive.
- `<CODEX_CONFIG_TOML>`: Codex config file path.

