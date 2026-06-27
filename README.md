<div align="center">

# EverMind

**A local-first context persistence system for AI-assisted software work.**

[![EverMind](https://img.shields.io/badge/EverMind-Context%20Persistence-2E86AB?style=flat-square)](https://github.com/YPYT1/EverMind)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](docs/quickstart-windows.md)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](docs/quickstart-macos.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)

[Quick Start](#installation-and-usage) · [Architecture](#system-architecture) · [Concepts](#core-concepts) · [Integrations](#integration-model) · [Docs](docs/README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md)

</div>

## Definition

EverMind is a local-first memory infrastructure layer for AI-assisted software engineering.

It persists project context across sessions, separates fast working memory from reviewed long-term knowledge, and gives coding agents a stable way to recover, search, evolve, and verify project knowledge.

EverMind is not an agent framework, not a vector database, and not a standalone RAG application. It is the persistence layer that keeps software knowledge available to agents over time.

## Problem Background

AI coding systems usually operate with a short-lived context window. Even when they can read files and call tools, they still lose important engineering context between sessions:

- why a module was designed in a specific way;
- which command verifies a behavior;
- where runtime data and generated artifacts live;
- which implementation detail caused a previous failure;
- which facts are stable enough to become project knowledge;
- which notes are temporary and should not pollute long-term documentation.

RAG and vector search help retrieve text, but they do not define a full knowledge lifecycle. Agent frameworks can orchestrate actions, but they usually do not own durable project memory. EverMind fills this gap.

## Core Solution

EverMind models memory as a lifecycle, not as a single storage operation.

The core abstraction is:

```text
working context -> searchable memory -> reviewed knowledge -> reusable project intelligence
```

This gives AI coding systems three properties that a raw retrieval layer does not provide:

- **continuity**: the next session can start from known project context;
- **structure**: memory is routed by project, agent, archive, and code graph concerns;
- **trust**: durable notes are reviewed before becoming official knowledge.

## System Architecture

EverMind is an infrastructure layer placed between AI coding agents and local memory stores.

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

### Why this architecture

The agent interface layer should stay replaceable. Codex, Claude Code, Cursor, and Devin have different configuration formats, but they need the same memory behavior.

The orchestration layer owns policy. It decides whether a fact should be recalled, remembered, proposed as a candidate, or ignored.

The local knowledge substrate owns persistence. It keeps memory, archive notes, and code graph state on the user's machine.

## Core Concepts

### Context Persistence

Project context should survive a chat session. EverMind gives agents a repeatable way to recover previous decisions, runtime conventions, known pitfalls, and verification practices.

### Memory Lifecycle

EverMind does not treat all memory as equal:

1. `briefing` restores project context at the beginning of work.
2. `recall` searches relevant prior memory.
3. `remember` stores useful working facts.
4. `propose_basic_memory_update` creates a reviewed archive candidate.
5. `commit_basic_memory_update` promotes a candidate only after explicit confirmation.

### Reviewed Knowledge

Long-term project knowledge should be stable, evidence-backed, and readable. EverMind Archive stores official knowledge as Markdown after review.

### Codebase Context

Software memory is not only prose. Agents also need architecture, call paths, snippets, and impact analysis. EverMind includes code graph access so memory can be grounded in repository structure.

### Local-First Operation

The default deployment keeps memory and project knowledge local. Future cloud modes are treated as optional synchronization strategies, not as a requirement.

## Core Capabilities

| Capability | What it provides |
| --- | --- |
| Session recovery | Start work with project briefing instead of cold reading. |
| Semantic recall | Search project facts, decisions, pitfalls, and preferences. |
| Working memory | Persist useful context during active development. |
| Reviewed archive | Convert stable facts into official Markdown knowledge only after confirmation. |
| Code graph understanding | Inspect architecture, code search, call paths, snippets, and impact. |
| Agent portability | Use the same memory system from Codex, Claude Code, Cursor, and Devin. |
| Local setup automation | Generate `.env`, MCP snippets, skill links, and health checks for Windows/macOS. |

## Use Cases

- Continue a feature after days or weeks without re-reading the entire repository.
- Ask an agent to recall previous architecture decisions before editing a module.
- Preserve test commands, runtime paths, and known pitfalls as project knowledge.
- Generate reviewed change notes after a coding task.
- Analyze code impact before modifying a shared function.
- Maintain a local knowledge base for multiple AI coding tools.

## Installation And Usage

<details>
<summary><strong>Windows: guided setup</strong></summary>

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\configure.ps1
```

</details>

<details>
<summary><strong>Windows: full bootstrap and check</strong></summary>

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1
```

</details>

<details>
<summary><strong>macOS: guided setup</strong></summary>

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
bash scripts/macos/configure.sh
```

</details>

<details>
<summary><strong>macOS: full bootstrap and check</strong></summary>

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
bash scripts/macos/bootstrap.sh
```

</details>

After setup, copy the generated MCP snippet for your tool:

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

Then ask your agent:

```text
Use EverMind. Start with briefing for this project, then recall known pitfalls.
```

## Integration Model

EverMind integrates through MCP and agent-side instruction files.

```text
Agent client
  -> generated MCP snippet
  -> uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
  -> EverMind MCP tools
  -> local memory, archive, and code graph layers
```

Supported templates:

- Codex: `agents/codex/AGENTS.md`
- Claude Code: `agents/claude-code/CLAUDE.md`
- Cursor: `agents/cursor/rules.md`
- Devin: `agents/devin/instructions.md`

## Configuration

EverMind uses two configuration surfaces:

- `config/evermind.example.yaml`: human-readable system reference.
- `.env.example`: runtime environment template copied to `.env`.

Common placeholders:

| Placeholder | Meaning |
| --- | --- |
| `<EVERMIND_ROOT>` | Path to this cloned repository. |
| `<EVEROS_ROOT>` | Local runtime data root. |
| `<EVERMIND_ARCHIVE_ROOT>` | Reviewed Markdown archive root. |

## Roadmap

- Improve non-interactive setup for managed machines.
- Expand archive templates for larger repositories.
- Add stronger diagnostics for MCP startup failures.
- Keep local-first as the default operating model.
- Reserve optional local-to-cloud synchronization modes without making cloud memory mandatory.

## Community and Support

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
