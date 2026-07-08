# EverMind MCP

EverMind MCP is the local-first MCP bridge shipped inside EverMind. It exposes the memory tools used by Codex, Claude Code, Cursor, Devin, and other MCP clients.

## Start

```bash
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

The parent EverMind setup renders ready-to-copy client snippets into `generated/mcp-config/`.

## Tools

EverMind MCP exposes 13 tools:

- `remember`
- `recall`
- `forget`
- `briefing`
- `list`
- `graph_explore`
- `status`
- `export`
- `compact`
- `tags`
- `reindex`
- `health`
- `list_spaces`

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

