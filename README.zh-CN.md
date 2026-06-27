<div align="center">

# EverMind

**面向 AI 辅助软件工程的本地优先上下文持久化系统。**

[![EverMind](https://img.shields.io/badge/EverMind-Context%20Persistence-2E86AB?style=flat-square)](https://github.com/YPYT1/EverMind)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](docs/quickstart-windows.md)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](docs/quickstart-macos.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)

[快速开始](#安装与使用) · [系统架构](#系统架构) · [核心概念](#核心概念) · [集成方式](#集成方式) · [文档](docs/README.zh-CN.md) · [English](README.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

</div>

## 一句话定义

EverMind 是一层面向 AI 辅助软件工程的本地记忆基础设施。

它让项目上下文能够跨会话持续存在，把快速工作记忆和经过审核的长期知识分开，并为 coding agents 提供恢复、检索、演化和验证项目知识的稳定入口。

EverMind 不是 Agent 框架，不是向量数据库，也不是单独的 RAG 应用。它更接近 AI 编码系统下面的上下文持久化层。

## 问题背景

AI coding agents 通常受限于短生命周期上下文。即使它们能读文件、能调用工具，也会在会话之间丢失关键工程语境：

- 某个模块为什么这样设计；
- 哪条命令能验证某个行为；
- 运行数据、索引和生成文件放在哪里；
- 之前失败过的实现细节是什么；
- 哪些事实已经稳定到可以成为项目知识；
- 哪些内容只是临时观察，不应该污染长期文档。

RAG 和向量搜索能帮助找文本，但它们没有定义完整的知识生命周期。Agent 框架能调度行为，但通常不负责项目知识的长期可信沉淀。EverMind 解决的正是这个中间层问题。

## 核心解决方案

EverMind 把记忆建模为生命周期，而不是一次存储操作。

核心抽象是：

```text
工作上下文 -> 可检索记忆 -> 已审核知识 -> 可复用项目智能
```

这让 AI 编码系统获得三个基础能力：

- **连续性**：下一次会话可以从已有项目上下文开始。
- **结构性**：记忆按项目、agent、长期档案和代码图谱分层路由。
- **可信性**：长期知识进入正式档案前需要经过候选和确认。

## 系统架构

EverMind 位于 AI coding agents 和本地知识存储之间。

```text
AI Coding Interfaces
  Codex / Claude Code / Cursor / Devin
  agent instructions and skills
  generated MCP configuration

EverMind Orchestration Layer
  setup and health checks
  EverMind MCP bridge
  memory routing
  write policy
  archive candidate flow
  code graph access

Local Knowledge Substrate
  realtime project memory
  reviewed Markdown archive
  repository graph index
  runtime configuration and local paths
```

这种结构让不同 agent 客户端可以共享同一种记忆语义；策略层负责决定记忆是检索、写入、生成候选还是忽略；本地知识层负责真正持久化。

## 核心概念

### 上下文持久化

项目上下文不应该随着聊天窗口消失。EverMind 让 agent 能恢复历史决策、运行约定、已知坑点和验证方式。

### 记忆生命周期

EverMind 不把所有记忆视为同一种数据：

1. `briefing`：任务开始时恢复项目上下文。
2. `recall`：检索相关历史记忆。
3. `remember`：保存有价值的工作事实。
4. `propose_basic_memory_update`：生成长期档案候选。
5. `commit_basic_memory_update`：用户确认后才提升为正式知识。

### 已审核知识

长期项目知识应该稳定、有证据、可阅读。EverMind Archive 使用 Markdown 保存正式知识，便于阅读、diff、备份和迁移。

### 代码库上下文

软件记忆不只是文字。Agent 还需要架构、调用链、代码片段和影响范围。EverMind 通过 Code Graph 把记忆与真实代码结构连接起来。

### 本地优先

默认部署把记忆和项目知识保留在本机。未来云同步可以作为可选模式，但不是 v1 的前提。

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 会话恢复 | 通过 briefing 启动任务，而不是每次冷启动阅读项目。 |
| 语义检索 | 检索项目事实、历史决策、坑点和偏好。 |
| 工作记忆 | 在开发过程中保存有价值的上下文。 |
| 审核式档案 | 只有确认后的事实才进入正式 Markdown 知识库。 |
| 代码图谱理解 | 支持架构、调用链、代码搜索、片段和影响分析。 |
| 多 agent 复用 | Codex、Claude Code、Cursor、Devin 可使用同一套记忆系统。 |
| 本地安装自动化 | 生成 `.env`、MCP snippets、skills 链接和健康检查。 |

## 使用场景

- 隔几天继续开发某个功能，不需要重新阅读整个仓库。
- 修改模块前，让 agent 回忆之前的架构决策。
- 把测试命令、运行路径和已知坑点沉淀成项目知识。
- 完成任务后生成带证据的变更记忆候选。
- 修改共享函数前分析调用链和影响范围。
- 在多个 AI 编码工具之间共享同一套本地项目记忆。

## 安装与使用

<details>
<summary><strong>Windows：交互式配置</strong></summary>

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\configure.ps1
```

</details>

<details>
<summary><strong>Windows：完整 bootstrap 和检查</strong></summary>

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1
```

</details>

<details>
<summary><strong>macOS：交互式配置</strong></summary>

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
bash scripts/macos/configure.sh
```

</details>

<details>
<summary><strong>macOS：完整 bootstrap 和检查</strong></summary>

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
bash scripts/macos/bootstrap.sh
```

</details>

配置后复制对应工具的 MCP 配置：

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

然后在 agent 中使用：

```text
Use EverMind. Start with briefing for this project, then recall known pitfalls.
```

## 集成方式

EverMind 通过 MCP 和 agent 指令文件接入。

```text
Agent client
  -> generated MCP snippet
  -> uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
  -> EverMind MCP tools
  -> local memory, archive, and code graph layers
```

模板位置：

- Codex：`agents/codex/AGENTS.md`
- Claude Code：`agents/claude-code/CLAUDE.md`
- Cursor：`agents/cursor/rules.md`
- Devin：`agents/devin/instructions.md`

## 路线图

- 改进托管机器上的非交互式安装。
- 扩展大型仓库的长期档案模板。
- 增强 MCP 启动失败诊断。
- 保持本地优先作为默认运行模式。
- 预留可选云同步，但不把云记忆作为强依赖。

## Community and Support

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
