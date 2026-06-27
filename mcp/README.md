# EverMind MCP

EverMind MCP is the local-first MCP bridge shipped inside EverMind. It exposes the memory tools used by Codex, Claude Code, Cursor, Devin, and other MCP clients.

## Start

```bash
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

The parent EverMind setup renders ready-to-copy client snippets into `generated/mcp-config/`.

## Tools

EverMind MCP exposes 9 tools:

- `list_spaces`
- `remember`
- `request_status`
- `recall`
- `briefing`
- `forget`
- `fetch_history`
- `propose_basic_memory_update`
- `commit_basic_memory_update`

## Configuration

Use the EverMind public environment variable names:

```text
EVERMIND_MCP_BACKEND=everos
EVERMIND_MCP_DEFAULT_SPACE=
EVERMIND_MCP_USER_ID=mcp-user
EVEROS_BASE_URL=http://127.0.0.1:3378
EVERMIND_ARCHIVE_ROOT=<archive-root>
EVERMIND_ARCHIVE_WRITE_POLICY=candidate
```

Use the generated parent-project snippets for normal client setup.

## Development

```bash
uv sync --group dev
uv run ruff check
uv run pytest -q
```

