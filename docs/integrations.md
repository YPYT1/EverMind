# Integrations

EverMind integrates with AI coding agents via MCP and skill files.

## Claude Code

**MCP config** (`claude_desktop_config.json`):
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

**Skill** — add to your project's `CLAUDE.md`:
```
$~/EverMind/skills/evermind/SKILL.md
```

Or use the provided `agents/claude-code/CLAUDE.md` as a template.

**Reference**: `agents/claude-code/`

---

## Cursor

**MCP config** (`~/.cursor/mcp.json` or `%APPDATA%\Cursor\User\globalStorage\cursor.mcp\mcp.json`):
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

**Rules** — add to your project's `.cursorrules` or Cursor rules:
Reference or copy `agents/cursor/rules.md`.

**Reference**: `agents/cursor/`

---

## Codex

**MCP config** (`.codex/config.toml`):
```toml
[mcp_servers.evermind]
type = "stdio"
command = "uv"
args = ["run", "--directory", "/path/to/EverMind/mcp", "evermind-mcp"]
```

**Agent instructions** — add to `AGENTS.md`:
Reference or copy `agents/codex/AGENTS.md`.

**Reference**: `agents/codex/`

---

## Devin

**MCP config** — add to Devin's MCP configuration:
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

**Instructions** — reference `agents/devin/instructions.md`.

**Reference**: `agents/devin/`

---

## How Memory Is Saved

In v2, create memories with `remember()` and correct existing memories with `update_memory()`:

```
remember("content", importance=0)   # temporary working note (24h)
remember("content", importance=1)   # long-term memory
remember("content", importance=2)   # permanent archive — never deleted
update_memory({"id":"...", "content":"corrected content"})  # fix a wrong memory in place
```

There is no separate propose/commit workflow. `importance=2` stores directly to the archive layer.

Memory type (episodic / semantic / procedural / decision / bug / preference) is auto-detected from content keywords.

---

## Offline Mode

EverMind works without network access and without optional dependencies:

| Mode | Requirements | Search quality |
|------|-------------|----------------|
| Keyword only | None (built-in FTS5) | Good for exact terms |
| Hybrid | `uv pip install sqlite-vec sentence-transformers` | Best |

Install hybrid search (recommended):
```bash
cd EverMind/mcp
uv pip install sqlite-vec sentence-transformers
```
