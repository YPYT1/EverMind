<div align="center">

<img src="./png/everymind.png" alt="EverMind" width="180" />

# EverMind

**本地优先的六层 AI 记忆系统，专为编程助手设计。**  
零配置。零云依赖。直接接入 Claude Code、Cursor、Codex。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?style=flat-square)](#架构)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](scripts/setup-windows.ps1)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](scripts/setup-macos.sh)

[快速开始](#快速开始) · [架构](#架构) · [MCP 工具](#mcp-工具) · [安装](#安装) · [文档](docs/README.md) · [English](README.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

</div>

---

## EverMind 是什么？

EverMind 为 AI 编程助手提供跨会话的持久记忆。它通过 MCP 直接嵌入 Claude Code、Cursor 和 Codex — 无需云服务，无需独立进程，无需 API Key，只需指向你的仓库即可使用。

记忆按照人类存储知识的方式组织为六层：自动过期的工作笔记、情节事件、语义事实、流程知识、永久归档决策，以及实体关系图谱。系统根据内容和重要性自动选择合适的层级。

## 行业问题

AI 助手在每次会话之间会遗忘一切：

- 某个模块为什么要这样设计
- 哪条命令真正能构建或测试项目
- 已知的 bug 及有效的修复方法
- 部署流程和注意事项
- 个人偏好和编码规范

EverMind 为 AI 助手提供一个可靠的地方来存储和检索这些知识。

## 架构

```text
          Claude Code / Cursor / Codex
                     |
                  MCP (stdio)
                     |
           +-----------------------+
           |   EverMind v2 核心    |
           |                       |
           |  remember / recall    |
           |  forget  / briefing   |
           +-----------+-----------+
                       |
           +-----------v-----------+
           |   SQLite              |
           |  (每个项目一个文件)   |
           |                       |
           |  第1层: 工作记忆      |  24小时自动过期
           |  第2层: 情节记忆      |  事件和发现
           |  第3层: 语义记忆      |  项目事实
           |  第4层: 流程记忆      |  操作知识
           |  第5层: 归档记忆      |  永久决策
           |  第6层: 图谱记忆      |  实体关系
           |                       |
           |  FTS5 关键词搜索      |
           |  sqlite-vec 向量搜索  |
           |  事件日志             |
           +-----------------------+
```

存储路径：`~/.evermind/<project-slug>.db` — 每个项目一个 SQLite 文件，从 git remote 自动推断项目名称。

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
```

### 2. 运行安装脚本

**Windows：**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

**macOS / Linux：**

```bash
bash scripts/setup-macos.sh
```

脚本会检查 Python 3.11+，在缺少时安装 uv，同步依赖，并自动配置 Claude Desktop 和 Cursor。

### 3. 手动配置（可选）

在 `claude_desktop_config.json` 中添加：

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

将 `/path/to/EverMind` 替换为实际的克隆路径，这是唯一需要修改的地方。

### 4. 启用向量搜索（可选，推荐）

```bash
cd mcp
uv pip install sqlite-vec sentence-transformers
```

不安装也可以使用 FTS5 关键词搜索。安装后，`recall()` 使用 BM25 + 向量 KNN 混合搜索，语义查询效果显著更好。

## MCP 工具

| 工具 | 说明 |
|------|------|
| `remember(content, importance, tags)` | 保存记忆。importance: 0=工作(24h), 1=长期, 2=永久 |
| `recall(query, limit, mode)` | 混合搜索：BM25+语义，自动从 git 检测项目空间 |
| `forget(id)` | 按 ID 删除记忆 |
| `briefing()` | 加载会话上下文：当前项目的最近和重要记忆 |

记忆类型从内容自动检测：bug 修复→情节记忆，架构决策→语义记忆，部署步骤→流程记忆。对于永远不想被删除的内容，设置 `importance=2`。

## 安装

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

脚本功能：
- 检查 Python 3.11+、uv、git
- 如未找到 uv，提供自动安装选项
- 在 mcp 目录运行 `uv sync`
- 自动更新 Claude Desktop 和 Cursor 的 MCP 配置
- 创建 `~/.evermind` 记忆目录

### macOS

```bash
bash scripts/setup-macos.sh
```

与 Windows 步骤相同，使用 macOS 配置路径（`~/Library/Application Support/Claude/`）。

### 手动安装

```bash
# 安装依赖
uv sync --directory mcp

# 可选：启用向量搜索（推荐）
cd mcp && uv pip install sqlite-vec sentence-transformers
```

## 记忆生命周期

| 层级 | 保留时间 | 用途 |
|------|---------|------|
| 工作记忆 | 24 小时 | 临时笔记、进行中的上下文 |
| 情节记忆 | 长期 | 事件、bug 修复、发现 |
| 语义记忆 | 长期 | 项目相关事实 |
| 流程记忆 | 长期 | 部署步骤、工作流、操作指南 |
| 归档记忆 | 永久 | 架构决策、永久规则 |
| 图谱记忆 | 永久 | 实体关系（Phase 3） |

- `importance=0` — 工作层（默认，24小时后过期）
- `importance=1` — 长期层（根据内容类型自动分类）
- `importance=2` — 归档层（永不删除）

## Agent 指令

在 `CLAUDE.md` 或 `AGENTS.md` 中添加：

```markdown
## EverMind Memory

Call briefing() at session start to restore project context.
Call remember(content) for anything worth keeping across sessions.
Call recall(query) before starting work on a feature or bug.

importance=0: temporary working note (default)
importance=1: long-term memory
importance=2: permanent archive (architecture decisions, critical bugs)
```

## 文档

- [架构设计](docs/architecture.md)
- [MCP 工具参考](docs/mcp-tools.md)
- [配置说明](docs/configuration.md)
- [Windows 快速开始](docs/quickstart-windows.md)
- [macOS 快速开始](docs/quickstart-macos.md)
- [故障排除](docs/troubleshooting.md)
- [v2 重设计方案](docs/v2-redesign.md)

---

<div align="center">
为希望 AI 工具真正记住事情的工程师而构建。
</div>
