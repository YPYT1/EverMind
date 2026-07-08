# Configuration

EverMind v2 requires zero configuration for basic use. The MCP server is self-contained — no external service to start, no API keys needed.

## Minimum Config (required)

Add this to your Claude Desktop `claude_desktop_config.json` or Cursor `mcp.json`:

```json
{
  "mcpServers": {
    "evermind": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/EverMind/mcp", "evermind-mcp"]
    }
  }
}
```

Replace `/path/to/EverMind` with the absolute path to your EverMind clone.

Windows path example: `C:\\Users\\you\\EverMind`

That's it. Everything else is auto-detected:
- **Project space**: detected from `git remote get-url origin` → `coding:<repo-slug>`
- **Database location**: `~/.evermind/<slug>.db`
- **Search mode**: FTS5 by default; hybrid if sqlite-vec is installed

## Optional Environment Variables

Set these in the `env` block of your MCP config, or in your shell environment.

| Variable | Default | What it does |
|----------|---------|--------------|
| `EVERMIND_HOME` | `~/.evermind` | Directory where SQLite databases are stored |
| `EVERMIND_DEFAULT_SPACE` | auto from git | Override project space (e.g. `coding:my-app`) |
| `EVERMIND_EMBED_MODEL` | `BAAI/bge-small-zh-v1.5` | Local embedding model name |
| `EVERMIND_EMBED_ENABLED` | `true` | Set to `false` to disable embedding entirely |
| `EVERMIND_LLM_API_KEY` | none | API key for LLM-powered fact extraction (optional) |
| `EVERMIND_LLM_MODEL` | `gpt-4o-mini` | LLM model for fact extraction |
| `EVERMIND_LLM_BASE_URL` | OpenAI | Custom LLM endpoint (e.g. OpenRouter) |

## Enable Vector Search (recommended)

```bash
cd /path/to/EverMind/mcp
uv pip install sqlite-vec sentence-transformers
```

After installing, `recall()` automatically switches to hybrid BM25 + vector search. The embedding model downloads once on first use (~22MB).

## MCP Config Templates

Ready-to-use config files are in `templates/mcp-config/`:

| File | Platform | Client |
|------|---------|--------|
| `claude-code.windows.json` | Windows | Claude Desktop |
| `claude-code.macos.json` | macOS | Claude Desktop |
| `cursor.windows.json` | Windows | Cursor |
| `cursor.macos.json` | macOS | Cursor |
| `codex.windows.toml` | Windows | Codex |
| `codex.macos.toml` | macOS | Codex |
| `devin.example.json` | Any | Devin |

Replace `<EVERMIND_ROOT>` with your actual EverMind clone path.
