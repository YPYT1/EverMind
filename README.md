<div align="center">

# EverMind

**A local-first memory suite for AI coding agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![MCP](https://img.shields.io/badge/MCP-ready-6f42c1)
![Windows](https://img.shields.io/badge/Windows-supported-0078D4)
![macOS](https://img.shields.io/badge/macOS-supported-000000)
![Local First](https://img.shields.io/badge/local--first-yes-brightgreen)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-orange)

[Quick Start](#quick-start) · [User Journey](docs/user-journey.md) · [MCP Tools](docs/mcp-tools.md) · [Configuration](docs/configuration.md) · [Architecture](docs/architecture.md) · [中文](README.zh-CN.md)

</div>

EverMind packages the pieces needed to give coding agents durable local memory:

- **EverOS** as the local memory runtime.
- **evermemos MCP** as the bridge for Codex, Claude Code, Cursor, Devin, and other MCP clients.
- **Basic Memory** as the reviewed Markdown project archive.
- **codebase-memory-mcp** as the code graph, architecture, call-path, and impact-analysis engine.
- **Skills** that teach agents how to read, search, and update memory responsibly.
- **Agent templates** for tool-specific instructions and MCP configuration.
- **Memory router and write policy templates** for automatic but review-safe persistence.

It is more complete than a plain memory MCP server because it ships the runtime contract, MCP bridge, skill behavior, agent rules, project-note templates, environment examples, and cross-platform checks together.

## Quick Start

```bash
git clone https://github.com/your-org/EverMind.git
cd EverMind
cp .env.example .env
```

For the simplest setup, run bootstrap:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts/windows/bootstrap.ps1
```

```bash
# macOS
bash scripts/macos/bootstrap.sh
```

Bootstrap creates local runtime folders, generates `.env`, installs/checks external tools, links skills into user skill folders, generates MCP snippets, and runs checks.

For a guided setup instead:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts/windows/configure.ps1
```

```bash
# macOS
bash scripts/macos/configure.sh
```

Configure asks for memory paths and model keys, installs skills into your user skill folders, and generates MCP snippets without overwriting existing client configs.

Then fill the model API keys in `.env`.

If you prefer manual steps, run:

For the full integrated stack, use:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts/windows/install-all.ps1
powershell -ExecutionPolicy Bypass -File scripts/windows/check-all.ps1
```

```bash
# macOS
bash scripts/macos/install-all.sh
bash scripts/macos/check-all.sh
```

If you only want to validate the EverMind repository skeleton, use:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts/windows/check.ps1
```

```bash
# macOS
bash scripts/macos/check.sh
```

Copy the generated MCP snippet for your tool from `generated/mcp-config/`. Static templates are also available in `templates/mcp-config/`.

The integrated installer also renders ready-to-copy snippets into `generated/mcp-config/`. It does not overwrite your Codex, Claude Code, Cursor, or Devin configuration.

If a template contains placeholders such as `<EVEROS_ROOT>` or `<BASIC_MEMORY_ROOT>`, replace them using [Configuration](docs/configuration.md). In short, `<EVEROS_ROOT>` is the EverOS runtime data directory, for example `D:\EverMindMemory\everos` on Windows or `$HOME/.evermind/everos` on macOS.

`.env.example` is the runtime environment template. It becomes `.env`, which scripts and MCP read at runtime. `config/evermind.example.yaml` is the single human-readable system config reference.

Once connected, ask your coding agent to call:

```text
briefing(space_id="coding:<your-project>")
recall(query="project architecture and known pitfalls", space_id="coding:<your-project>")
```

## What Is Included

```text
config/       One unified readable config example for the full stack.
mcp/          The evermemos MCP bridge files directly, without nested project directory.
skills/       One umbrella skill plus three focused memory skills.
agents/       Codex, Claude Code, Cursor, and Devin templates.
templates/    Basic Memory project files and MCP snippets.
scripts/      Windows/macOS install and check helpers.
docs/         Architecture, quickstarts, integrations, and troubleshooting.
third_party.lock.yaml  External component versions and license metadata.
```

## Memory Workflow

1. **Before work**: load a `briefing`, then use `recall` for project decisions, pitfalls, and configuration.
2. **During work**: search memory when context is uncertain; verify facts against real files.
3. **After work**: create a Basic Memory candidate with stable facts and evidence.
4. **Only after review**: commit the candidate into the official project notes.

This keeps fast semantic memory separate from reviewed long-term knowledge.

## Safety Defaults

- Local EverOS API binds to `127.0.0.1` by default.
- API keys stay in `.env` and are ignored by git.
- Basic Memory official notes use candidate-first writes.
- Agent templates tell assistants not to store secrets, tokens, cookies, or private keys.

See [Security](docs/security.md) before exposing any service beyond loopback.

## External Components

EverMind uses a unified installer instead of vendoring upstream source code.

- Basic Memory: AGPL-3.0, installed with `uv tool install basic-memory==0.22.1`.
- codebase-memory-mcp: MIT, installed from the pinned GitHub release binary.

See [Components](docs/components.md) and `third_party.lock.yaml`.
