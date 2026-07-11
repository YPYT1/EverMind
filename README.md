<div align="center">

<img src="./png/everymind.png" alt="EverMind" width="420" />

**Local-first 6-layer AI memory system for coding agents.**  
Zero config. Zero cloud. Runs inside Claude Code, Cursor, and Codex.

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?style=flat-square)](#architecture)
[![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue?style=flat-square)](LICENSE)
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
           |  codebase + archive   |
           +-----------+-----------+
                       |
           +-----------v-----------+
           |   SQLite              |
           |   (shared catalog)    |
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

Storage: `~/.evermind/catalog.db` — one shared local catalog. Project and
workspace IDs record provenance and affect ranking; they do not hide memories.

## How EverMind Works

EverMind has two components that work together:

**MCP Server** — the tools Claude Code calls directly:

| Tool group | What it does |
|------|-------------|
| Memory tools | `briefing`, `remember`, `recall`, `forget`, `graph_explore`, `status`, `health`, etc. |
| Codebase tools | `index_repository`, `get_architecture`, `search_code`, `search_graph`, `trace_path`, etc. |
| Archive tools | `search_notes`, `read_note`, `write_note`, `propose_basic_memory_update`, `commit_basic_memory_update`, etc. |

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

The script checks Python 3.12+, installs uv if missing, syncs dependencies, and auto-configures Claude Desktop and Cursor.

### Codebase and archive engines

EverMind exposes 50 tools through the same `evermind` MCP server: 14 memory
tools, 13 code graph tools, 20 local Basic Memory tools, 2 reviewed archive
update tools, and 1 unified project lifecycle tool. Basic Memory executes from
the vendored source in process. Code exploration uses the vendored MIT
`codebase-memory-mcp` C/tree-sitter/Hybrid-LSP engine; official bundles require
its verified internal binary. No external Basic Memory CLI, cloud account, or
PATH-installed codebase-memory binary is required.

For new projects, run `index_repository`, then `get_architecture`/`search_code`, then save verified findings:

```
remember("Tech stack: ...", importance=1, tags=["codebase-verified"], meta={"source":"codebase"})
remember("Entry point: ...", importance=1, tags=["codebase-verified"], meta={"source":"codebase"})
remember("Key structure: ...", importance=1, tags=["codebase-verified"], meta={"source":"codebase"})
```

Verified negative facts can outrank older unverified memories and produce `forget_suggestions` when conflicts are detected.

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

### 4. Semantic search

Offline English and Chinese semantic retrieval is included by default using the
bundled `intfloat/multilingual-e5-small` model. When an external embedding or
rerank API is configured and healthy, EverMind prefers it and falls back to the
local profile on failure. No API key is required for the local baseline.

## MCP Tools

| Tool | Purpose |
|------|---------|
| `remember(content, importance, tags)` | Save to memory. importance: 0 = working (24h), 1 = long-term, 2 = permanent |
| `update_memory(id, content, tags, meta)` | Correct an existing memory without deleting it; rebuilds search, embeddings, graph links, and briefing cache |
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
- Checks Python 3.12+, uv, git
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

# Include sqlite-vec and Chinese tokenization acceleration
uv sync --directory mcp --extra full
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
