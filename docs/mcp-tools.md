# MCP Tools

EverMind ships the evermemos MCP bridge directly under `mcp/`.

The MCP server is complete for the local memory workflow and currently exposes 9 tools:

| Tool | Purpose |
| --- | --- |
| `list_spaces` | List memory spaces visible to the MCP server. |
| `remember` | Store information into EverOS realtime memory. Sensitive content is blocked by default. |
| `request_status` | Check whether a prior `remember` request has completed extraction/indexing. |
| `recall` | Search relevant memories by query across one or more spaces. |
| `briefing` | Restore structured project/session context at the start of work. |
| `fetch_history` | Page through historical memory items chronologically. |
| `forget` | Request deletion of memories. In local EverOS mode this does not edit Markdown directly. |
| `propose_basic_memory_update` | Create a reviewed Basic Memory candidate for durable project notes. |
| `commit_basic_memory_update` | Commit a candidate into official Basic Memory notes; requires `confirmed=true`. |

## Startup

MCP clients should start the stdio server with:

```text
uv run --directory <EVERMIND_ROOT>/mcp evermemos-mcp
```

Manual terminal testing:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/start-mcp.ps1
```

```bash
bash scripts/macos/start-mcp.sh
```

In normal use, Codex, Claude Code, Cursor, or Devin starts MCP automatically from its MCP config.

The source directory must be `<EVERMIND_ROOT>/mcp`. Older examples that add an extra nested MCP child directory are not valid for this integrated layout.
