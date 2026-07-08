# Quick Start — macOS

## Prerequisites

- Python 3.11 or newer — https://www.python.org/downloads/
- Git — usually pre-installed; verify with `git --version`

## 1. Clone

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
```

## 2. Run the setup script

```bash
bash scripts/setup-macos.sh
```

The script will:
- Check Python 3.11+ and uv (offers to install uv if missing)
- Install EverMind and all dependencies (`uv sync --extra full`)
- Auto-configure Claude Desktop and Cursor MCP configs
- Tell you how to add the `$evermind` skill to your project

## 3. Restart Claude Desktop or Cursor

After setup completes, restart your AI client to load the new MCP config.

## 4. Add the EverMind skill to your project

In your project's `CLAUDE.md` or `AGENTS.md`, add:

```markdown
$~/EverMind/skills/evermind/SKILL.md
```

Or copy the content of `agents/claude-code/CLAUDE.md` into your project's CLAUDE.md.

## 5. Verify it works

Open a project in Claude Code. Ask Claude: "Call briefing()". You should see:

```json
{"space": "coding:your-project", "memory_count": 0, ...}
```

`memory_count: 0` is normal for a new project. Claude will explore the codebase and seed initial memories automatically.

## Manual Configuration

If you prefer manual setup instead of the script, add this to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Replace `/path/to/EverMind` with your actual clone path.

## Enable Vector Search (optional, recommended)

```bash
cd EverMind/mcp
uv pip install sqlite-vec sentence-transformers
```

Without this, EverMind uses keyword search only. With it, `recall()` uses hybrid BM25 + semantic search.

**Note on offline mode**: Even without vector search installed, EverMind fully works using FTS5 keyword search. The `recall()` tool gracefully falls back to keyword-only mode and reports `"mode": "fts"` instead of `"mode": "hybrid"`.

## Troubleshooting

See [docs/troubleshooting.md](troubleshooting.md) for common issues.
