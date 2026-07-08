# Quick Start — Windows

## Prerequisites

- Python 3.11 or newer — https://www.python.org/downloads/
- Git — https://git-scm.com/download/win

## 1. Clone

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
```

## 2. Run the setup script

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
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
$D:\path\to\EverMind\skills\evermind\SKILL.md
```

Or copy the content of `agents/claude-code/CLAUDE.md` into your project's CLAUDE.md.

## 5. Verify it works

Open a project in Claude Code. Ask Claude: "Call briefing()". You should see:

```json
{"space": "coding:your-project", "memory_count": 0, ...}
```

`memory_count: 0` is normal for a new project. Claude will explore the codebase and seed initial memories automatically.

## Manual Configuration

If you prefer to configure manually instead of using the setup script, add this to your Claude Desktop `claude_desktop_config.json` (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "evermind": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\path\\to\\EverMind\\mcp", "evermind-mcp"]
    }
  }
}
```

Replace `C:\\path\\to\\EverMind` with your actual clone path.

## Enable Vector Search (optional, recommended)

```powershell
cd EverMind\mcp
uv pip install sqlite-vec sentence-transformers
```

Without this, EverMind uses keyword search only. With it, `recall()` uses hybrid BM25 + semantic search for significantly better results.

## Troubleshooting

See [docs/troubleshooting.md](troubleshooting.md) for common issues.
