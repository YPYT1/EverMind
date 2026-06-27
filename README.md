<div align="center">

# EverMind

**Local-first AI Memory OS for Coding Agents**

[![EverMind](https://img.shields.io/badge/EverMind-AI%20Memory%20System-2E86AB?style=flat-square)](https://github.com/YPYT1/EverMind)
[![Local First](https://img.shields.io/badge/local--first-true-2ECC71?style=flat-square)](docs/architecture.md)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![AI Agents](https://img.shields.io/badge/AI%20Agents-coding%20ready-F39C12?style=flat-square)](docs/integrations.md)
[![Memory Runtime](https://img.shields.io/badge/memory-runtime-active-1ABC9C?style=flat-square)](docs/components.md)
[![Graph Memory](https://img.shields.io/badge/codebase-graph%20memory-34495E?style=flat-square)](docs/components.md)
[![Skills](https://img.shields.io/badge/skills-engine-supported-E67E22?style=flat-square)](docs/skills.md)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](docs/quickstart-windows.md)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](docs/quickstart-macos.md)

[Quick Start](#quick-start) · [User Journey](docs/user-journey.md) · [MCP Tools](docs/mcp-tools.md) · [Configuration](docs/configuration.md) · [Architecture](docs/architecture.md) · [中文](README.zh-CN.md)

</div>

EverMind packages the pieces a coding agent needs into one system:

- **EverMind Runtime** for local memory retrieval and storage.
- **EverMind MCP** for Codex, Claude Code, Cursor, Devin, and other MCP clients.
- **EverMind Skills** for consistent memory-first agent behavior.
- **EverMind Archive** for reviewed long-term Markdown project notes.
- **EverMind Code Graph** for repository structure, call-path, and impact analysis.

Users install one project, run one setup flow, copy one MCP snippet, and then use `briefing`, `recall`, and `remember` from their agent.

## Quick Start

```bash
git clone https://github.com/your-org/EverMind.git
cd EverMind
cp .env.example .env
```

Guided setup:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/configure.ps1
```

```bash
bash scripts/macos/configure.sh
```

Full bootstrap:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/bootstrap.ps1
```

```bash
bash scripts/macos/bootstrap.sh
```

Setup creates local runtime folders, generates `.env`, installs user skills, renders MCP snippets into `generated/mcp-config/`, and checks the stack. Existing Codex, Claude Code, Cursor, and Devin configs are not overwritten.

Normal MCP client command:

```text
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

## Layout

```text
mcp/          EverMind MCP bridge.
skills/       EverMind agent skills.
agents/       Codex, Claude Code, Cursor, and Devin templates.
templates/    Project archive and MCP config templates.
scripts/      Windows/macOS setup, startup, and check helpers.
config/       One readable unified config example.
docs/         Architecture, user journey, integrations, and troubleshooting.
```

`config/evermind.example.yaml` is the human-readable full-system config reference. `.env.example` is the runtime template copied to `.env`; put local paths and API keys there, and do not commit `.env`.

## Workflow

1. **Before work**: call `briefing` for the project and `recall` for task keywords.
2. **During work**: write useful live context with `remember`; use EverMind Code Graph for code structure and impact questions.
3. **After work**: create an EverMind Archive candidate for stable facts, evidence, and validation results.
4. **After confirmation**: commit the candidate into official project notes only when the user explicitly confirms.

## Compliance

EverMind keeps third-party dependency and license information in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [third_party.lock.yaml](third_party.lock.yaml).

## Community and Support

Thanks for supporting EverMind. If this project helps your local AI memory workflow, a star, issue, pull request, or small donation all help keep it moving.

<div align="center">
  <p><strong>Join the EverMind community group</strong></p>
  <img src="png/EverMind3群.png" alt="EverMind community group QR code" width="260">
</div>

<div align="center">
  <p><strong>Support the project</strong></p>
  <img src="png/Alipay.jpg" alt="Alipay support QR code" width="220">
  <img src="png/wecha.png" alt="WeChat support QR code" width="220">
</div>
