# Components

EverMind v2 consists of three components:

## MCP Server

The MCP server is a Python package (`mcp/src/evermind_mcp/`) started by the AI client via `uv run`. It exposes 4 tools over stdio transport.

**Entry point**: `evermind_mcp.server_v2:main_sync`

**Key modules**:
- `server_v2.py` — 4-tool MCP server, tool dispatch
- `memory_service_v2.py` — business logic: remember, recall, briefing, dedup
- `storage.py` — SQLite + FTS5 + sqlite-vec storage layer
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

## Code Graph (Optional)

`evermind-code-graph` is a separate MCP tool (not included in this repo) that indexes repository structure and exposes graph traversal, code search, and call path tracing. EverMind's skills and agent instructions use it during codebase exploration.

## Storage

One SQLite file per project: `~/.evermind/<project-slug>.db`

Tables:
- `memories` — all stored memories with layer/type/importance metadata
- `memories_fts` — FTS5 virtual table for BM25 keyword search
- `memory_vecs` — sqlite-vec virtual table for KNN vector search (optional)
- `graph_nodes` / `graph_edges` — entity relationship graph (Phase 3)
- `event_log` — audit trail of all memory operations
- `briefing_cache` — pre-materialized session context (<5ms load)
