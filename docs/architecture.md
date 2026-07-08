# Architecture

## Overview

EverMind is a two-component system: an MCP server that provides memory tools, and skill files that shape agent behavior.

```
              Claude Code / Cursor / Codex
                        |
                     MCP (stdio)
                        |
              +-----------------------+
              |   EverMind v2 Core    |
              |                       |
              |  briefing / remember  |
              |  recall   / forget    |
              +-----------+-----------+
                          |
              +-----------v-----------+
              |   SQLite (embedded)   |
              |   ~/.evermind/<slug>  |
              |                       |
              | Layer 1: working      | 24h auto-expire
              | Layer 2: episodic     | events/bugs
              | Layer 3: semantic     | project facts
              | Layer 4: procedural   | workflows
              | Layer 5: archive      | permanent
              | Layer 6: graph        | relationships (Phase 3)
              |                       |
              | FTS5 keyword search   |
              | sqlite-vec KNN search |
              | event log             |
              +-----------------------+
```

## Components

### MCP Server (`mcp/src/evermind_mcp/`)

The MCP server is a Python package started by the AI client via `uv run`. It exposes 4 tools:

- `briefing()` — load session context from pre-materialized cache (<5ms)
- `remember(content, importance)` — store to SQLite with auto type detection
- `recall(query)` — hybrid BM25 + vector KNN search with RRF fusion
- `forget(id)` — delete a memory

No external service. No HTTP. No API keys needed for basic use.

### Skills (`skills/`)

Skill files are Markdown documents loaded by agent instruction systems (`$skill-name` syntax in CLAUDE.md). They tell the agent:
- When to call briefing/remember/recall
- What to do for a new project (explore codebase, seed memory)
- How to classify what's worth remembering

Skills are separate from the MCP server — they shape behavior, not capability.

### Storage

One SQLite file per project: `~/.evermind/<project-slug>.db`

Project slug is auto-detected from `git remote get-url origin`.

Tables: `memories`, `memories_fts` (FTS5), `memory_vecs` (sqlite-vec, optional), `graph_nodes`, `graph_edges`, `event_log`, `briefing_cache`.

## Memory Write Path

```
remember(content)
  |
  +-- exact dedup check (SQLite, ~1ms)
  |   if identical content exists: merge, return
  |
  +-- INSERT into memories + FTS5 index (~5ms)
  +-- return id immediately (<20ms total)
  |
  +-- [background, non-blocking]
        +-- generate embedding -> store in sqlite-vec (~50-300ms)
        +-- refresh briefing_cache
```

## Memory Read Path

```
recall(query)
  |
  +-- FTS5 BM25 search (~5ms)
  +-- sqlite-vec KNN search (~10-20ms, if available)
  |
  +-- RRF fusion: score = 1/(60+rank_fts) + 1/(60+rank_vec)
  +-- return top-k ranked results (<30ms total)
```

## 6-Layer Memory Model

Based on cognitive science memory taxonomy:

| Layer | Importance | Retention | Content type |
|-------|-----------|-----------|--------------|
| working | 0 | 24h | Scratch notes, WIP |
| episodic | 1 | Long | Events: bugs, discoveries |
| semantic | 1 | Long | Facts: tech stack, decisions |
| procedural | 1 | Long | Workflows: deploy, build |
| archive | 2 | Permanent | Architecture decisions |
| graph | — | Permanent | Entity relationships |
