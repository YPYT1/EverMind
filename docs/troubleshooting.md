# Troubleshooting

## MCP Connection Issues

### "evermind" not showing in Claude Desktop / Cursor

1. Check the MCP config path is correct:
   ```json
   "args": ["run", "--directory", "/path/to/EverMind/mcp", "evermind-mcp"]
   ```
   Replace `/path/to/EverMind` with the absolute path to your EverMind clone.

2. Run the smoke test to verify the install:
   ```bash
   cd /path/to/EverMind
   uv run --directory mcp python -c "from evermind_mcp.storage import EmbeddedStorage; print('OK')"
   ```

3. If uv is not found: install it from https://github.com/astral-sh/uv
   ```bash
   # macOS/Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # Windows (PowerShell)
   irm https://astral.sh/uv/install.ps1 | iex
   ```

4. If dependencies are missing:
   ```bash
   uv sync --directory /path/to/EverMind/mcp --extra full
   ```

5. Restart Claude Desktop or Cursor after changing the config.

### Tools return errors on first use

`briefing()` returning `memory_count: 0` is **normal** on first use — it means no memories exist yet. The database file is created automatically on first `remember()` or `recall()` call.

The database lives at `~/.evermind/<project-slug>.db`. The project slug is auto-detected from your git remote URL.

---

## Vector Search Not Working

If `recall()` only uses keyword search (mode: "fts" instead of "hybrid"), vector search is not installed.

Install it:
```bash
cd /path/to/EverMind/mcp
uv pip install sqlite-vec sentence-transformers
```

The first time you call `remember()` or `recall()` after installing, EverMind will download the embedding model (~22MB for BAAI/bge-small-zh-v1.5). Subsequent calls use the cached model.

To use a different embedding model:
```bash
# Set in your shell or MCP server env:
EVERMIND_EMBED_MODEL=all-MiniLM-L6-v2
```

---

## Project Space Not Detected

EverMind auto-detects your project name from `git remote get-url origin`. If you see unexpected space names or `coding:default`:

- Make sure you're running Claude Code / Cursor inside a git repository
- Make sure the repo has a remote: `git remote -v`
- Override manually: set `EVERMIND_DEFAULT_SPACE=coding:my-project` in the MCP server env block

---

## Memory Not Persisting Across Sessions

Memories are stored in `~/.evermind/<slug>.db`. If they're not persisting:

1. Confirm the database exists: `ls ~/.evermind/`
2. Confirm the project slug is the same across sessions (it comes from git remote)
3. Check for errors in Claude Desktop's MCP logs

---

## Performance

| Operation | Expected | If slower |
|-----------|----------|-----------|
| `briefing()` | < 5ms | Database may be very large — use `forget()` to prune |
| `recall()` FTS | < 30ms | Normal |
| `recall()` hybrid | < 100ms | First call loads embedding model (~2s), subsequent calls fast |
| `remember()` | < 20ms | Background embedding queue may be long |

---

## Common Mistakes

**Do not** add EverOS env vars (`EVERMIND_MCP_BACKEND`, `EVEROS_BASE_URL`, etc.) to your MCP config. These are v1 variables and have no effect in v2. The only configuration needed is the path to the EverMind `mcp/` directory.

**Do not** run a separate EverOS service. EverMind v2 is fully embedded — there is no HTTP service to start.
