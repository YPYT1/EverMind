<div align="center">

<img src="./png/everymind.png" alt="EverMind" width="420" />

**Local-first 6-layer AI memory system for coding agents.**  
Zero config. Zero cloud. Runs inside Claude Code, Cursor, and Codex.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?style=flat-square)](#architecture)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](scripts/setup-windows.ps1)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](scripts/setup-macos.sh)

[Quick Start](#quick-start) · [Architecture](#architecture) · [Tools](#mcp-tools) · [Setup](#setup) · [Docs](docs/README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

</div>

---

## What is EverMind?

EverMind gives AI coding agents persistent memory across sessions. It embeds directly into Claude Code, Cursor, and Codex via MCP — no cloud, no separate server, no API keys required, no configuration beyond pointing it at your repo.

Memory is organized into 6 layers modeled after how humans store knowledge: working notes that expire, episodic events, semantic facts, procedural knowledge, permanent archive decisions, and a graph of entity relationships. The right layer is chosen automatically based on content and importance.

## The Problem

AI agents forget everything between sessions:

- Why a module was designed a certain way
- Which command actually builds or tests the project
- Known bugs and the fixes that worked
- Deployment procedures and pitfalls
- Personal preferences and coding conventions

EverMind solves this by giving agents a reliable place to store and retrieve that knowledge.

## Architecture

```text
          Claude Code / Cursor / Codex
                     |
                  MCP (stdio)
                     |
           +-----------------------+
           |   EverMind v2 Core    |
           |                       |
           |  remember / recall    |
           |  forget  / briefing   |
           +-----------+-----------+
                       |
           +-----------v-----------+
           |   SQLite              |
           |   (one file/project)  |
           |                       |
           |  Layer 1: working     |  24h auto-expire
           |  Layer 2: episodic    |  events & discoveries
           |  Layer 3: semantic    |  project facts
           |  Layer 4: procedural  |  how-to knowledge
           |  Layer 5: archive     |  permanent decisions
           |  Layer 6: graph       |  entity relationships (auto-extracted from content)
           |                       |
           |  FTS5 keyword search  |
           |  sqlite-vec KNN       |
           |  event log            |
           +-----------------------+
```

Storage: `~/.evermind/<project-slug>.db` — one SQLite file per project, name auto-detected from git remote.

## How EverMind Works

EverMind has two components that work together:

**MCP Server** — the tools Claude Code calls directly:

| Tool | What it does |
|------|-------------|
| `briefing()` | Load project context at session start |
| `remember(content, importance)` | Save information to memory |
| `recall(query)` | Search memory (keyword + semantic) |
| `forget(id)` | Delete a specific memory |

**Skills** — instruction files that tell Claude *when* and *how* to use the tools:

- `skills/evermind/SKILL.md` — core workflow: session start protocol, when to remember
- `skills/evermind-archive/SKILL.md` — permanent knowledge patterns
- `skills/evermind-code-graph/SKILL.md` — codebase exploration
- `skills/project-memory/SKILL.md` — first-time project initialization

Reference a skill from your `CLAUDE.md` or `AGENTS.md`:

```markdown
$evermind
```

Or with full path if the skill isn't on your skills search path:

```markdown
$D:/path/to/EverMind/skills/evermind/SKILL.md
```

> **Both components are needed.** The MCP server gives Claude the ability to remember things. The skills tell Claude when to use that ability.

## Quick Start

### 1. Clone

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
```

### 2. Run the setup script

**Windows:**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

**macOS / Linux:**

```bash
bash scripts/setup-macos.sh
```

The script checks Python 3.11+, installs uv if missing, syncs dependencies, and auto-configures Claude Desktop and Cursor.

### About evermind-code-graph

EverMind's session start protocol uses `evermind-code-graph` to explore the codebase when opening a new project. This is a **separate optional tool** not included in this repository.

**If you have evermind-code-graph installed:** the new-project initialization runs automatically as described.

**If you don't have evermind-code-graph:** use this fallback for new project initialization:

```
remember("Tech stack: <manually describe languages, frameworks, databases>", importance=1)
remember("Entry point: <main file> — run with: <command>", importance=1)
remember("Key structure: <brief description of main folders and their purpose>", importance=1)
```

You can gather this information by reading the README, package.json/pyproject.toml/Cargo.toml, and main entry files yourself.

---

### 3. Manual config (optional)

Add to your `claude_desktop_config.json`:

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

Replace `/path/to/EverMind` with the actual clone path. That is the only required change.

### 4. Enable vector search (optional but recommended)

```bash
cd mcp
uv pip install sqlite-vec sentence-transformers
```

Without these, EverMind uses FTS5 keyword search. With them, `recall()` runs hybrid BM25 + vector KNN — significantly better for semantic queries like "what did we decide about the auth module".

## MCP Tools

| Tool | Purpose |
|------|---------|
| `remember(content, importance, tags)` | Save to memory. importance: 0 = working (24h), 1 = long-term, 2 = permanent |
| `recall(query, limit, mode)` | Hybrid BM25 + semantic search. Auto-detects project from git |
| `forget(id)` | Delete a memory by ID |
| `briefing()` | Load session context: recent + important memories for this project |
| `list(layer, tags, limit)` | List memories filtered by layer and/or tags |
| `graph_explore(entity)` | Explore entity relationships in the knowledge graph |

Memory type is auto-detected from content: bug fixes → episodic, architecture decisions → semantic, deploy steps → procedural. Set `importance=2` for things you never want deleted.

## Setup

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

What the script does:
- Checks Python 3.11+, uv, git
- Offers to install uv if not found
- Runs `uv sync` in the mcp directory
- Auto-updates Claude Desktop and Cursor MCP configs
- Creates `~/.evermind` memory directory

### macOS

```bash
bash scripts/setup-macos.sh
```

Same steps as Windows, using macOS config paths (`~/Library/Application Support/Claude/`).

### Manual install

```bash
# Install dependencies
uv sync --directory mcp

# Optional: vector search (recommended)
cd mcp && uv pip install sqlite-vec sentence-transformers
```

## Memory Lifecycle

| Layer | Retention | Use for |
|-------|-----------|---------|
| working | 24 hours | Temporary notes, WIP context |
| episodic | Long-term | Events, bug fixes, discoveries |
| semantic | Long-term | Facts about the project |
| procedural | Long-term | Deploy steps, workflows, how-to |
| archive | Permanent | Architecture decisions, permanent rules |
| graph | Permanent | Entity relationships (auto-extracted from content) |

- `importance=0` — working layer (default, expires in 24h)
- `importance=1` — long-term layer (auto-classified by content type)
- `importance=2` — archive layer (never deleted)

## Agent Instructions

Add to `CLAUDE.md` or `AGENTS.md`:

```markdown
## EverMind Memory

Call briefing() at session start to restore project context.
Call remember(content) for anything worth keeping across sessions.
Call recall(query) before starting work on a feature or bug.

importance=0: temporary working note (default)
importance=1: long-term memory
importance=2: permanent archive (architecture decisions, critical bugs)
```

## Docs

- [Architecture](docs/architecture.md)
- [MCP Tools Reference](docs/mcp-tools.md)
- [Configuration](docs/configuration.md)
- [Quickstart Windows](docs/quickstart-windows.md)
- [Quickstart macOS](docs/quickstart-macos.md)
- [Troubleshooting](docs/troubleshooting.md)
- [v2 Redesign Notes](docs/v2-redesign.md)

---

## Community & Support

<div align="center">

<img src="./png/EverMind3群.png" width="200" /><br/>
<sub>Join the EverMind community</sub>

</div>

<br/>

<div align="center">

<table>
<tr>
<td align="center">
<img src="./png/wecha.png" width="200"/><br/>
<sub>Community</sub>
</td>

<td align="center">
<img src="./png/Alipay.jpg" width="200"/><br/>
<sub>Support EverMind development</sub>
</td>
</tr>
</table>

</div>

<div align="center">
Built for engineers who want their AI tools to actually remember things.
</div>
