# User Journey

## Overview

EverMind works through two components:
1. **MCP Server** — gives Claude the `briefing / remember / recall / forget` tools
2. **Skills** — tell Claude when and how to use those tools

Both must be set up for EverMind to work as intended.

---

## First-Time Setup (10 minutes)

### Step 1: Install

Run the setup script for your platform:

```bash
# macOS
bash scripts/setup-macos.sh

# Windows
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

The script installs dependencies, configures Claude Desktop and Cursor, and tells you what to do next.

### Step 2: Add skill to your project

In the project you want EverMind to remember, add to `CLAUDE.md` (or `AGENTS.md` for Codex):

```
$~/EverMind/skills/evermind/SKILL.md
```

This tells Claude Code to follow the EverMind session protocol.

### Step 3: Restart Claude Desktop or Cursor

Changes to MCP config require a restart.

---

## Daily Workflow

### Session start (automatic with skill loaded)

Claude calls `briefing()` automatically at session start.

**New project** (memory_count = 0):
Claude explores the codebase with evermind-code-graph and saves initial facts.
Next session starts with full context already loaded.

**Returning project** (memory_count > 0):
Claude reads recent and important memories, immediately has project context.

### During work

Claude calls `recall(query)` before starting any feature or investigation.
Claude calls `remember(content, importance=1)` when finding useful information.
Claude calls `remember(content, importance=2)` for permanent architecture decisions.

### Nothing to configure between sessions

Memories persist automatically in `~/.evermind/<project-slug>.db`.

---

## Memory Lifecycle

| Layer | How to store | Retention |
|-------|-------------|-----------|
| working | remember(importance=0) | 24h, auto-deleted |
| episodic/semantic/procedural | remember(importance=1) | Long-term |
| archive | remember(importance=2) | Permanent |

---

## Available Skills

| Skill | Use for |
|-------|---------|
| `skills/evermind/SKILL.md` | Core workflow — load in every project |
| `skills/evermind-archive/SKILL.md` | Guidance on writing permanent memories |
| `skills/evermind-code-graph/SKILL.md` | Codebase exploration with code graph |
| `skills/project-memory/SKILL.md` | Initializing a brand-new project's memory |
