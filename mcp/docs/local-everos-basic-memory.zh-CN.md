# 本地 EverOS + Basic Memory 融合模式

这份文档描述本 fork 的本机记忆运行方式。目标是保留 `evermemos-mcp`
原有 MCP 工具体验，同时把后端切到本机 EverOS，并让 Basic Memory 只作为
确认后的中文项目档案馆。

## 路径与端口

| 项目 | 固定路径 |
|---|---|
| EverOS 源码 | `<EVEROS_REPO>` |
| evermemos-mcp fork | `<EVERMIND_ROOT>\mcp` |
| EverOS 记忆根目录 | `<EVEROS_ROOT>` |
| Basic Memory 根目录 | `<BASIC_MEMORY_ROOT>` |

EverOS API 固定绑定：

```powershell
http://127.0.0.1:3378
```

不要使用官方默认的 `8000` 端口，避免和其他本地服务冲突。

## evermemos-mcp 环境变量

```powershell
EVERMEMOS_BACKEND=everos
EVEROS_BASE_URL=http://127.0.0.1:3378
EVEROS_ROOT=<EVEROS_ROOT>
EVEROS_TIMEOUT_SECONDS=180
BASIC_MEMORY_ROOT=<BASIC_MEMORY_ROOT>
BASIC_MEMORY_WRITE_POLICY=candidate
```

Cloud 模式仍可用，但本地融合模式不需要 `EVERMEMOS_API_KEY`。EverOS
自身仍需要 LLM / embedding / rerank 配置；这些 key 应写入
`<EVEROS_ROOT>\everos.toml` 或 EverOS 支持的环境变量，不能写进本仓库。

## 空间映射

| MCP space_id | EverOS 映射 |
|---|---|
| `coding:coord-picker` | `app_id=coding`, `project_id=coord-picker`, `user_id=mcp-user` |
| `chat:preferences` | `app_id=chat`, `project_id=preferences`, `user_id=mcp-user` |
| `agent:codex` | `app_id=agent`, `project_id=codex`, `agent_id=codex` |

`agent:*` 空间默认检索 `agent_case` 和 `agent_skill`。普通 `coding:*` 和
`chat:*` 空间默认检索 `profile` 与 `episodic_memory`。

## MCP 工具行为

| 工具 | 本地 EverOS 行为 |
|---|---|
| `remember` | 调 EverOS `/api/v1/memory/add`；`flush=true` 时再调 `/api/v1/memory/flush` |
| `recall` | 调 `/api/v1/memory/search`，并映射为原 evermemos 返回结构 |
| `briefing` | 聚合 profile / episode / agent memory；`coding:*` 额外附带 Basic Memory 中文摘要 |
| `fetch_history` | 调 `/api/v1/memory/get` |
| `forget` | 返回 `UNSUPPORTED_OPERATION`，不直接删除或编辑本地 Markdown |
| `propose_basic_memory_update` | 只写候选 JSON 到 `<BASIC_MEMORY_ROOT>\.candidates` |
| `commit_basic_memory_update` | 只有 `confirmed=true` 时才直接写入 `<BASIC_MEMORY_ROOT>\projects\<project-slug>\*.md` 正式中文档案 |

`commit_basic_memory_update` 不再调用 `uvx basic-memory tool edit-note/write-note`。
原因是 Basic Memory CLI 在部分 Windows 长内容写入场景会长时间阻塞，导致 MCP
工具等待 300 秒后超时。当前实现直接维护 Markdown 文件和 frontmatter，
Basic Memory 文件库仍然是正式档案来源，写入结果会返回
`write_method=direct_markdown`。

## 启动 EverOS

首次准备：

```powershell
cd <EVEROS_REPO>
uv sync --python 3.12
uv run --python 3.12 everos init --root <EVEROS_ROOT>
```

然后编辑 `<EVEROS_ROOT>\everos.toml`，配置本机可用的 LLM / embedding / rerank provider。当前本机方案使用 DeepSeek 兼容接口作为 LLM，SiliconFlow 的 Qwen embedding / rerank 模型作为向量化与重排能力。

密钥只能写入 `<EVEROS_ROOT>\everos.toml` 或本机环境变量，不能写进仓库、MCP 配置片段、skill 或 `AGENTS.md`。

手动启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <EVERMIND_ROOT>\mcp\scripts\start-everos-3378.ps1
```

健康检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <EVERMIND_ROOT>\mcp\scripts\check-everos-3378.ps1
```

## NSSM 开机自启

注册或更新 NSSM 服务必须在“以管理员身份运行”的 PowerShell 中执行。普通非管理员会话只能手动启动 EverOS，不能写入 Windows 服务注册表。

注册或更新 EverOS 服务：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <EVERMIND_ROOT>\mcp\scripts\install-everos-nssm-service.ps1
```

注册并立即启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <EVERMIND_ROOT>\mcp\scripts\install-everos-nssm-service.ps1 -StartNow
```

默认服务名是 `EverOSMemory3378`，日志写入：

```text
<EVEROS_ROOT>\logs\everos-service.out.log
<EVEROS_ROOT>\logs\everos-service.err.log
```

`evermemos-mcp` 本身是 MCP stdio server，应该由 Codex / Claude Code /
Cursor 按会话拉起，不建议注册成后台常驻 Windows 服务。


## Codex 本地接入

Codex 作为主要客户端时，推荐在 `<CODEX_CONFIG_TOML>` 中使用 `mcp_servers.evermemos` stdio server，并设置以下环境变量：

```toml
[mcp_servers.evermemos]
type = "stdio"
command = "uv"
args = ["run", "--directory", "D:\\Project\\evermemos-mcp", "evermemos-mcp"]

[mcp_servers.evermemos.env]
EVERMEMOS_BACKEND = "everos"
EVEROS_BASE_URL = "http://127.0.0.1:3378"
EVEROS_ROOT = "D:\\EverOSMemory"
EVEROS_TIMEOUT_SECONDS = "180"
BASIC_MEMORY_ROOT = "D:\\BasicMemory"
BASIC_MEMORY_WRITE_POLICY = "candidate"
```

`evermemos-mcp` 不需要常驻为 Windows 服务；Codex 会按会话拉起。EverOS 才需要由 NSSM 常驻。

## 客户端配置片段

本地融合模式配置片段：

```text
docs\mcp-config-snippets\codex-everos-local.json
docs\mcp-config-snippets\claude-code-everos-local.json
docs\mcp-config-snippets\cursor-everos-local.json
```

## 验收命令

EverOS 3378 健康检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <EVERMIND_ROOT>\mcp\scripts\check-everos-3378.ps1
```

本地记忆闭环：

```powershell
cd <EVERMIND_ROOT>\mcp
uv run python scripts\smoke_test_everos_local.py
```

单元测试：

```powershell
cd <EVERMIND_ROOT>\mcp
uv run pytest tests\test_config.py tests\test_server.py tests\test_memory_service.py tests\test_everos_client.py tests\test_basic_memory_bridge.py -q
```



