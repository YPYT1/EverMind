# EverMind MCP

EverMind MCP 是 EverMind 内置的本地优先 MCP 接口，供 Codex、Claude Code、Cursor、Devin 和其他 MCP 客户端调用；记忆、代码图谱和归档能力都走源码深度融合路线。

## 启动

```bash
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

父级 EverMind 配置脚本会把可复制的客户端配置生成到 `generated/mcp-config/`。

## 工具

EverMind MCP 暴露 50 个工具：

- 14 个 memory 工具：`remember`, `update_memory`, `recall`, `forget`, `briefing`, `list`, `graph_explore`, `status`, `export`, `compact`, `tags`, `reindex`, `health`, `list_spaces`
- 13 个 codebase graph 工具：`index_repository`, `list_projects`, `index_status`, `search_graph`, `trace_path`, `detect_changes`, `query_graph`, `get_graph_schema`, `get_code_snippet`, `get_architecture`, `search_code`, `manage_adr`, `ingest_traces`
- 20 个本地 Basic Memory 工具：`build_context`, `canvas`, `create_memory_project`, `delete_note`, `edit_note`, `fetch`, `list_directory`, `list_memory_projects`, `move_note`, `read_content`, `read_note`, `recent_activity`, `release_notes`, `schema_diff`, `schema_infer`, `schema_validate`, `search`, `search_notes`, `view_note`, `write_note`
- 2 个审核后归档更新工具：`propose_basic_memory_update`, `commit_basic_memory_update`
- 1 个统一项目生命周期工具：`delete_project`

## 配置

使用本地 `.env` 配置运行时。MCP 客户端配置只负责启动服务器进程。

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

外部 API 完全可选；未配置时默认使用内置本地多语言模型。正常客户端接入请使用父项目生成的配置片段。

## 开发

```bash
uv sync --group dev
uv run ruff check
uv run pytest -q
```

