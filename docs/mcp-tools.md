# MCP Tools

EverMind ships EverMind MCP directly under `mcp/`.

Start command:

```text
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

Most users do not run this manually. Codex, Claude Code, Cursor, or Devin starts it from the MCP config.

## Tool List

EverMind MCP exposes 9 tools.

| Tool | Purpose | Typical timing |
| --- | --- | --- |
| `list_spaces` | List memory spaces visible to the MCP server. | Setup, debugging, advanced routing. |
| `remember` | Store useful information into realtime memory. Sensitive content is blocked by default. | During work. |
| `request_status` | Check whether a prior write has completed extraction or indexing. | After writes. |
| `recall` | Search relevant memories by query across one or more spaces. | Before and during work. |
| `briefing` | Restore structured project or session context at the start of work. | Task start. |
| `fetch_history` | Page through historical memory items chronologically. | Auditing or timeline review. |
| `forget` | Request deletion of memories when supported by the backend. | Cleanup or correction. |
| `propose_basic_memory_update` | Create a reviewed EverMind Archive candidate for durable project notes. | Task end. |
| `commit_basic_memory_update` | Commit a candidate into official archive notes; requires `confirmed=true`. | After explicit confirmation. |

## Recommended Agent Pattern

At task start:

```text
briefing(project=<current project>)
recall(query=<task keywords>)
```

During work:

```text
remember(content=<stable useful fact>)
recall(query=<unclear historical decision>)
```

At task end:

```text
propose_basic_memory_update(...)
```

After user confirmation:

```text
commit_basic_memory_update(confirmed=true, ...)
```

## Memory Spaces

EverMind works best when memory is scoped. Recommended conventions:

- `coding:<project-slug>` for project memory;
- `agent:codex` or similar for agent behavior notes;
- `chat:preferences` for cross-project user preferences.

The project slug is usually the repository folder name normalized to lowercase.

## Safety

Do not use memory tools to store:

- API keys;
- tokens;
- passwords;
- cookies;
- private keys;
- session credentials;
- unrelated personal data.

Archive writes should include evidence such as file paths, commands, test results, or service status.

