# Agents

EverMind agent templates are conservative by design. They prioritize reliable local memory over clever but risky automation.

## Shared Rules

All templates instruct agents to:

- read memory before substantial code changes;
- verify remembered facts in files before editing;
- use code graph analysis when architecture or impact is unclear;
- create EverMind Archive candidates after meaningful changes;
- commit official notes only after explicit confirmation;
- never save secrets.

## Template Files

| Agent | Behavior file | MCP config |
| --- | --- | --- |
| Codex | `agents/codex/AGENTS.md` | `agents/codex/config-snippet.toml` |
| Claude Code | `agents/claude-code/CLAUDE.md` | `agents/claude-code/mcp-config.json` |
| Cursor | `agents/cursor/rules.md` | `agents/cursor/mcp-config.json` |
| Devin | `agents/devin/instructions.md` | `agents/devin/mcp-config.json` |

Generated versions are written to `generated/mcp-config/`.

## What Is Deliberately Not Included

The templates do not include:

- reverse engineering workflows;
- offensive security workflows;
- malware analysis workflows;
- penetration-testing rules;
- platform-specific private instructions.

EverMind is meant to be a general local memory system for coding agents.

