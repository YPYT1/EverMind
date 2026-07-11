# Components

EverMind v2 consists of three components:

## EverMind MCP Server

The MCP server is a Python package (`mcp/src/evermind_mcp/`) started by the AI client via `uv run`. It exposes 50 tools over stdio: 14 memory, 13 code graph, 20 local Basic Memory, 2 reviewed archive update, and 1 unified project lifecycle tool.

**Entry point**: `evermind_mcp.server_v2:main_sync`

**Key modules**:
- `server_v2.py` — unified MCP server and tool dispatch
- `memory_service_v2.py` — business logic: remember, recall, briefing, dedup
- `storage.py` — SQLite + FTS5 + sqlite-vec storage layer
- `codebase_engine.py` — built-in EverMind source-fused code graph engine
- `archive_engine.py` — reviewed archive candidate workflow
- `provider_boundary.py` — explicit local/cloud provider boundary for future modes
- `tool_errors.py` — shared machine-readable error envelopes
- `embedding.py` — bundled local multilingual embeddings with optional external enhancement
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

EverMind exposes code graph and archive capabilities through the same MCP server. The local code graph engine uses the vendored MIT `codebase-memory-mcp` source and internal binary for tree-sitter and Hybrid-LSP graph extraction. Official bundles reject an incomplete engine instead of silently using the Python fallback. Local Basic Memory tools execute in process from `third_party/basic-memory`; the two EverMind archive update tools retain the candidate/confirmation workflow. Users do not need PATH-installed Basic Memory or codebase-memory services.

## Storage

One shared local catalog: `~/.evermind/catalog.db`

Tables:
- `memories` — all stored memories with layer/type/importance metadata
- `memories_fts` — FTS5 virtual table for BM25 keyword search
- `memory_vecs` — sqlite-vec virtual table for KNN vector search (optional)
- `graph_nodes` / `graph_edges` — entity relationship graph (Phase 3)
- `event_log` — audit trail of all memory operations
- `briefing_cache` — pre-materialized session context (<5ms load)
