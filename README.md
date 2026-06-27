<div align="center">

# EverMind

**Local-first AI memory system for coding agents**

[![EverMind](https://img.shields.io/badge/EverMind-AI%20Memory%20System-2E86AB?style=flat-square)](https://github.com/YPYT1/EverMind)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](docs/quickstart-windows.md)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](docs/quickstart-macos.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-orange?style=flat-square)](docs/README.md)

[Quick Start](#quick-start) · [How It Works](#how-it-works) · [MCP Tools](docs/mcp-tools.md) · [Integrations](docs/integrations.md) · [Docs](docs/README.md) · [中文](README.zh-CN.md)

</div>

EverMind is a complete local memory system for AI coding agents. It gives Codex, Claude Code, Cursor, Devin, and other MCP-capable tools a shared way to read project context, remember useful facts, build reviewed long-term notes, and inspect code structure.

EverMind is not just a single memory MCP. It packages the whole workflow:

- **EverMind Runtime**: local realtime memory storage and retrieval.
- **EverMind MCP**: the bridge that exposes memory tools to agents.
- **EverMind Skills**: repeatable agent behavior for reading, searching, and writing memory.
- **EverMind Archive**: reviewed Markdown project knowledge for durable facts.
- **EverMind Code Graph**: repository structure, call-path, code search, and impact analysis.
- **EverMind Setup**: Windows/macOS scripts that install, configure, render snippets, and check the stack.

The default mode is local-first. Cloud memory is only a future adapter path, not a requirement for v1.

## Quick Start

### Windows

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind

# Guided setup. It creates .env, renders MCP snippets, and installs user skills.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\configure.ps1

# Or run the full bootstrap flow.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1
```

If you already installed the external engines and only want EverMind config:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\install-all.ps1 -SkipToolInstall
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\check-all.ps1
```

### macOS

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind

# Guided setup.
bash scripts/macos/configure.sh

# Or run the full bootstrap flow.
bash scripts/macos/bootstrap.sh
```

If you already installed the external engines and only want EverMind config:

```bash
bash scripts/macos/install-all.sh --skip-tool-install
bash scripts/macos/check-all.sh
```

After setup, copy the generated snippet for your tool:

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

Normal MCP start command:

```text
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

Then ask your agent:

```text
Use EverMind. Start with briefing for this project, then recall known pitfalls.
```

## How It Works

EverMind uses a three-layer architecture:

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

The important design choice is separation of memory speed and memory trust:

- `remember` writes useful realtime context for later recall.
- `briefing` restores structured context at the beginning of a task.
- `recall` searches memories by query and space.
- `propose_basic_memory_update` creates a reviewed archive candidate.
- `commit_basic_memory_update` writes official archive notes only after explicit confirmation.

This keeps agents helpful without letting them silently pollute long-term project documentation.

## Repository Layout

```text
mcp/          EverMind MCP bridge and tests.
skills/       Agent skills for memory-first workflows.
agents/       Codex, Claude Code, Cursor, and Devin templates.
templates/    Archive templates and MCP config templates.
scripts/      Windows/macOS setup, startup, and check helpers.
config/       One human-readable unified config example.
docs/         Architecture, usage, integration, security, and troubleshooting docs.
tests/        Top-level integration and release-readiness checks.
```

## Configuration

EverMind intentionally has two configuration surfaces:

- `config/evermind.example.yaml`: readable full-system reference for humans.
- `.env.example`: runtime environment template copied to `.env` for local paths and API keys.

Do not commit `.env`. Keep API keys in `.env` or your shell environment.

Common placeholders:

| Placeholder | Meaning |
| --- | --- |
| `<EVERMIND_ROOT>` | Path to this cloned repository. |
| `<EVEROS_ROOT>` | Local runtime data root for memory files, indexes, logs, and runtime config. |
| `<EVERMIND_ARCHIVE_ROOT>` | Reviewed Markdown archive root. |

More detail: [Configuration](docs/configuration.md).

## Documentation

- [Documentation Index](docs/README.md)
- [Windows Quickstart](docs/quickstart-windows.md)
- [macOS Quickstart](docs/quickstart-macos.md)
- [Architecture](docs/architecture.md)
- [Components](docs/components.md)
- [MCP Tools](docs/mcp-tools.md)
- [Integrations](docs/integrations.md)
- [Skills](docs/skills.md)
- [Write Policy](docs/write-policy.md)
- [Security](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Local to Cloud Roadmap](docs/local-to-cloud-roadmap.md)

## Compliance

EverMind presents one product experience, while third-party source, license, and version information is kept transparent in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [third_party.lock.yaml](third_party.lock.yaml).

## Community

Issues and pull requests are welcome. If EverMind helps your local AI memory workflow, a star or small contribution helps the project move forward.

<div align="center">
  <p><strong>EverMind community group</strong></p>
  <img src="png/EverMind3群.png" alt="EverMind community group QR code" width="260">
</div>

<div align="center">
  <p><strong>Support the project</strong></p>
  <img src="png/Alipay.jpg" alt="Alipay support QR code" width="220">
  <img src="png/wecha.png" alt="WeChat support QR code" width="220">
</div>
