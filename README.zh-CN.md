<div align="center">

# EverMind

**面向 AI Coding Agents 的本地优先记忆系统**

[![EverMind](https://img.shields.io/badge/EverMind-AI%20Memory%20System-2E86AB?style=flat-square)](https://github.com/YPYT1/EverMind)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](docs/quickstart-windows.md)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](docs/quickstart-macos.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-orange?style=flat-square)](docs/README.zh-CN.md)

[快速开始](#快速开始) · [工作原理](#工作原理) · [MCP 工具](docs/mcp-tools.md) · [工具集成](docs/integrations.md) · [文档索引](docs/README.zh-CN.md) · [English](README.md)

</div>

EverMind 是一套给 AI coding agents 使用的完整本地记忆系统。它让 Codex、Claude Code、Cursor、Devin 以及其他支持 MCP 的工具，可以用同一套方式读取项目上下文、检索历史事实、沉淀长期中文档案，并分析代码结构和影响范围。

EverMind 不只是一个 memory MCP。它把一整套使用体验收在一个仓库里：

- **EverMind Runtime**：本地实时记忆存储和检索。
- **EverMind MCP**：暴露给 agent 使用的 MCP 工具入口。
- **EverMind Skills**：让 agent 形成“开发前读记忆、开发中检索、开发后沉淀”的稳定行为。
- **EverMind Archive**：人工确认后的 Markdown 长期项目档案。
- **EverMind Code Graph**：代码结构、调用链、代码搜索和变更影响分析。
- **EverMind Setup**：Windows/macOS 安装、配置、生成 snippets 和健康检查脚本。

默认模式是 local-first。云记忆只是未来预留，不是 v1 必须依赖。

## 快速开始

### Windows

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind

# 推荐：交互式配置，会创建 .env、生成 MCP snippets、安装用户 skills。
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\configure.ps1

# 或者：一键 bootstrap。
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1
```

如果你的机器已经安装过外部引擎，只想生成 EverMind 配置：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\install-all.ps1 -SkipToolInstall
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\check-all.ps1
```

### macOS

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind

# 推荐：交互式配置。
bash scripts/macos/configure.sh

# 或者：一键 bootstrap。
bash scripts/macos/bootstrap.sh
```

如果你的机器已经安装过外部引擎，只想生成 EverMind 配置：

```bash
bash scripts/macos/install-all.sh --skip-tool-install
bash scripts/macos/check-all.sh
```

配置完成后，把对应工具的生成文件复制到客户端配置中：

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

MCP 标准启动命令：

```text
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

然后在 agent 中说：

```text
Use EverMind. Start with briefing for this project, then recall known pitfalls.
```

## 工作原理

EverMind 采用三层架构：

```text
Agent Layer
  Codex / Claude Code / Cursor / Devin
  skills + agent instructions + generated MCP config

Memory Orchestration Layer
  installer/checker
  EverMind MCP
  memory router
  write policy
  future cloud sync adapter

Storage Layer
  local realtime memory
  reviewed Markdown archive
  local code graph index
  optional future cloud memory
```

核心设计是把“快速记忆”和“可信长期知识”分开：

- `remember`：写入实时上下文，方便之后检索。
- `briefing`：在任务开始时恢复项目上下文。
- `recall`：按关键词和空间检索历史记忆。
- `propose_basic_memory_update`：生成长期档案候选。
- `commit_basic_memory_update`：只有用户明确确认后，才写入正式长期档案。

这样 agent 可以主动记忆，但不会静默污染正式项目文档。

## 仓库结构

```text
mcp/          EverMind MCP bridge 和测试。
skills/       面向 agent 的记忆工作流技能。
agents/       Codex、Claude Code、Cursor、Devin 模板。
templates/    长期档案模板和 MCP 配置模板。
scripts/      Windows/macOS 配置、启动和检查脚本。
config/       单文件统一配置示例。
docs/         架构、使用、集成、安全和排障文档。
tests/        顶层集成与发布就绪检查。
```

## 配置说明

EverMind 有两类配置文件：

- `config/evermind.example.yaml`：给人看的完整系统配置参考。
- `.env.example`：运行时环境变量模板，复制成 `.env` 后填写本机路径和 API key。

不要提交 `.env`。API key 应该放在 `.env` 或本机 shell 环境中。

常见占位符：

| 占位符 | 含义 |
| --- | --- |
| `<EVERMIND_ROOT>` | 当前 EverMind 仓库路径。 |
| `<EVEROS_ROOT>` | 本地 runtime 数据根目录，用于记忆文件、索引、日志和运行配置。 |
| `<EVERMIND_ARCHIVE_ROOT>` | 人工确认后的 Markdown 长期档案根目录。 |

详细说明见：[配置说明](docs/configuration.md)。

## 文档

- [中文文档索引](docs/README.zh-CN.md)
- [Windows 快速开始](docs/quickstart-windows.md)
- [macOS 快速开始](docs/quickstart-macos.md)
- [架构](docs/architecture.md)
- [组件说明](docs/components.md)
- [MCP 工具](docs/mcp-tools.md)
- [工具集成](docs/integrations.md)
- [Skills](docs/skills.md)
- [写入策略](docs/write-policy.md)
- [安全](docs/security.md)
- [排障](docs/troubleshooting.md)
- [本地到云路线图](docs/local-to-cloud-roadmap.md)

## 合规

EverMind 对用户呈现一个完整产品体验，同时把第三方来源、许可证和版本集中透明地保留在 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [third_party.lock.yaml](third_party.lock.yaml)。

## 社区

欢迎 issue 和 pull request。如果 EverMind 对你的本地 AI 记忆工作流有帮助，star、反馈或小额支持都会让项目继续向前。

<div align="center">
  <p><strong>EverMind 交流群</strong></p>
  <img src="png/EverMind3群.png" alt="EverMind 交流群二维码" width="260">
</div>

<div align="center">
  <p><strong>支持项目</strong></p>
  <img src="png/Alipay.jpg" alt="支付宝支持二维码" width="220">
  <img src="png/wecha.png" alt="微信支持二维码" width="220">
</div>
