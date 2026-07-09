# Components

EverMind v2 consists of three components:

## EverMind MCP Server

The MCP server is a Python package (`mcp/src/evermind_mcp/`) started by the AI client via `uv run`. It exposes 42 tools over stdio transport: memory, codebase graph, and archive tools.

**Entry point**: `evermind_mcp.server_v2:main_sync`

**Key modules**:
- `server_v2.py` — unified MCP server and tool dispatch
- `memory_service_v2.py` — business logic: remember, recall, briefing, dedup
- `storage.py` — SQLite + FTS5 + sqlite-vec storage layer
- `codebase_engine.py` — Codebase Memory CLI bridge
- `archive_bridge.py` — Basic Memory CLI/candidate bridge
- `tool_bridge.py` — subprocess JSON/text command bridge
- `embedding.py` — optional local sentence-transformers with background queue
- `project_detector.py` — git remote → project slug auto-detection
- `config_v2.py` — zero-config loader, 4 optional env vars
- `types_v2.py` — shared dataclasses (MemoryRow, BriefingData)

## Skills

Skill files in `skills/` shape how AI agents use the MCP tools. They are loaded via `$skill-name` syntax in CLAUDE.md, AGENTS.md, or .cursorrules.

Available skills:
- `skills/evermind/SKILL.md` — core session workflow
- `skills/evermind-archive/SKILL.md` — permanent memory patterns
- `skills/evermind-code-graph/SKILL.md` — codebase exploration
- `skills/project-memory/SKILL.md` — first-time initialization

## Code Graph and Archive Engines

EverMind exposes Codebase Memory and Basic Memory through the same MCP server. The code graph bridge calls the bundled `codebase-memory-mcp` executable. The archive bridge calls the installed `basic-memory` CLI and keeps Basic Memory writes behind the candidate/confirmation workflow.

## Storage

One SQLite file per project: `~/.evermind/<project-slug>.db`

Tables:
- `memories` — all stored memories with layer/type/importance metadata
- `memories_fts` — FTS5 virtual table for BM25 keyword search
- `memory_vecs` — sqlite-vec virtual table for KNN vector search (optional)
- `graph_nodes` / `graph_edges` — entity relationship graph (Phase 3)
- `event_log` — audit trail of all memory operations
- `briefing_cache` — pre-materialized session context (<5ms load)
