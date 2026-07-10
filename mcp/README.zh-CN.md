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

公开配置统一使用 EverMind 变量名：

```text
EVERMIND_MCP_BACKEND=everos
EVERMIND_MCP_DEFAULT_SPACE=
EVERMIND_MCP_USER_ID=mcp-user
EVEROS_BASE_URL=http://127.0.0.1:3378
EVERMIND_ARCHIVE_ROOT=<archive-root>
EVERMIND_ARCHIVE_WRITE_POLICY=candidate
```

正常客户端接入请使用父项目生成的配置片段。

## 开发

```bash
uv sync --group dev
uv run ruff check
uv run pytest -q
```

