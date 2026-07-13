# EverMind MCP

EverMind MCP is the local-first MCP interface shipped inside EverMind. It exposes source-fused memory, codebase graph, and archive tools used by Codex, Claude Code, Cursor, Devin, and other MCP clients.

## Start

```bash
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

The parent EverMind setup renders ready-to-copy client snippets into `generated/mcp-config/`.

## Tools

EverMind MCP exposes 50 tools:

- 14 memory tools: `remember`, `update_memory`, `recall`, `forget`, `briefing`, `list`, `graph_explore`, `status`, `export`, `compact`, `tags`, `reindex`, `health`, `list_spaces`
- 13 codebase graph tools: `index_repository`, `list_projects`, `index_status`, `search_graph`, `trace_path`, `detect_changes`, `query_graph`, `get_graph_schema`, `get_code_snippet`, `get_architecture`, `search_code`, `manage_adr`, `ingest_traces`
- 20 local Basic Memory tools: `build_context`, `canvas`, `create_memory_project`, `delete_note`, `edit_note`, `fetch`, `list_directory`, `list_memory_projects`, `move_note`, `read_content`, `read_note`, `recent_activity`, `release_notes`, `schema_diff`, `schema_infer`, `schema_validate`, `search`, `search_notes`, `view_note`, `write_note`
- 2 reviewed archive update tools: `propose_basic_memory_update`, `commit_basic_memory_update`
- 1 unified project lifecycle tool: `delete_project`

## Configuration

Use a local `.env` file for runtime configuration. Keep MCP client config
focused on starting the server process.

```text
EVERMIND_DEFAULT_SPACE=coding:my-project
EVERMIND_SILICONFLOW_API_KEY=sk-...
EVERMIND_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
EVERMIND_EMBED_PROVIDER=siliconflow
EVERMIND_EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EVERMIND_EMBED_DIM=512
EVERMIND_RERANK_ENABLED=true
EVERMIND_RERANK_MODEL=Qwen/Qwen3-Reranker-8B
EVERMIND_LLM_ENABLED=true
EVERMIND_LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

Use the generated parent-project snippets for normal client setup.

## Development

```bash
uv sync --group dev
uv run ruff check
uv run pytest -q
```

