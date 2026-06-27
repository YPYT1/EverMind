# EverMind

**面向 AI coding agents 的本地优先长期记忆套件。**

EverMind 把 EverOS runtime、evermemos MCP、skills、agent 配置模板和 Basic Memory 中文项目档案模板组合到一个开源项目里，让 Codex、Claude Code、Cursor、Devin 等工具可以共享同一套本地记忆工作流。

融合版还会统一安装和检查 Basic Memory 与 codebase-memory-mcp：Basic Memory 负责审核后的 Markdown 长期档案，codebase-memory-mcp 负责代码图谱、架构、调用链和影响分析。EverMind 不复制上游源码，而是通过统一安装器锁版本、安装、配置和健康检查。

## 五分钟上手

```bash
git clone https://github.com/your-org/EverMind.git
cd EverMind
cp .env.example .env
```

最简单的一键入口：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/bootstrap.ps1
```

```bash
bash scripts/macos/bootstrap.sh
```

bootstrap 会创建本地运行目录、生成 `.env`、安装/检查外部工具、把 skills 放入用户目录并链接到 Codex/Claude、生成 MCP 配置片段，并运行检查。

如果你想一步一步交互式配置，先运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/configure.ps1
```

```bash
bash scripts/macos/configure.sh
```

`configure` 适合普通用户：它会询问本地记忆目录和模型 key，自动生成 `.env`、安装 skills 到用户目录，并生成 MCP 配置片段。它不会覆盖你已有的 Codex、Claude Code、Cursor 或 Devin 配置。

填写 `.env` 中的模型 key，然后运行检查：

完整融合版：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/install-all.ps1
powershell -ExecutionPolicy Bypass -File scripts/windows/check-all.ps1
```

```bash
bash scripts/macos/install-all.sh
bash scripts/macos/check-all.sh
```

只检查 EverMind 项目骨架：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/check.ps1
```

```bash
bash scripts/macos/check.sh
```

优先从 `generated/mcp-config/` 复制 bootstrap 生成好的 MCP 配置；静态模板仍保留在 `templates/mcp-config/`。

如果模板里出现 `<EVEROS_ROOT>`、`<BASIC_MEMORY_ROOT>` 这类占位符，请看 [`docs/configuration.md`](docs/configuration.md)。简单说：`<EVEROS_ROOT>` 是 EverOS 保存本地记忆、索引、日志和运行配置的目录，不是源码目录。例如 Windows 可填 `D:\EverMindMemory\everos`，macOS 可填 `$HOME/.evermind/everos`。

`.env.example` 是运行时环境变量模板，用来生成 `.env`，脚本和 MCP 读取它；`config/evermind.example.yaml` 是给人看的单文件完整系统配置说明。

## 组成

- `mcp/`：直接放 evermemos MCP bridge 文件，不再嵌套子目录。
- `config/`：只保留一个统一配置示例 `evermind.example.yaml`，集中说明完整系统配置。
- `skills/`：一个总技能 `evermind`，以及 `basic-memory`、`codebase-memory`、`project-memory` 三个独立技能。
- `agents/`：Codex、Claude Code、Cursor、Devin 的配置模板。
- `templates/basic-memory-project/`：中文项目长期档案模板。
- `scripts/`：Windows/macOS 安装和健康检查脚本。
- `third_party.lock.yaml`：外部依赖版本、许可证和安装方式。

## 用户目录安装方式

`scripts/*/setup-user.*` 会把 `skills/` 下的技能安装到用户目录：

- 主目录：`~/.agents/skills`
- 如果存在 Codex：链接到 `~/.codex/skills`
- 如果存在 Claude：链接到 `~/.claude/skills`

Windows 默认使用符号链接，权限不足时自动复制；也可以用 `-CopySkillsInsteadOfSymlink` 强制复制。macOS 可设置 `COPY_INSTEAD_OF_SYMLINK=1`。

## 核心工作流

1. 开发前：读取 `briefing`，再用 `recall` 查历史决策、坑点、运行配置。
2. 开发中：遇到不确定的模块边界或旧坑，优先检索本地记忆，再核对真实代码。
3. 开发后：把稳定事实、证据路径和验证结果生成 Basic Memory 候选。
4. 用户确认后：才提交到正式中文长期档案。

默认不自动覆盖你的 Codex、Claude Code、Cursor 或 Devin 配置；首版提供模板和检查脚本，保证可读、可复制、可审计。

## 外部组件

- Basic Memory：AGPL-3.0，通过 `uv tool install basic-memory==0.22.1` 安装。
- codebase-memory-mcp：MIT，通过固定 GitHub release 二进制安装。

EverMind 负责融合安装和统一配置，不把 AGPL 上游源码复制进本仓库。
