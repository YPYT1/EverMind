---
name: evermind
description: Core EverMind memory skill. Use at the start of every session and after meaningful work. Provides one unified MCP with memory, codebase, and archive tools. No external service required for basic use.
---

# EverMind Skill

EverMind gives AI coding agents persistent local memory across sessions.
It exposes one MCP tool surface: 14 EverMind memory tools, 14 built-in code graph tools, and 14 built-in archive tools. Basic use needs no cloud, external CLI, or API keys.

## Two-Component Architecture

EverMind has two parts that work together:

1. **MCP Server** — provides memory tools plus built-in source-fused codebase and archive engine tools
2. **Skills** — shape agent behavior so the tools are used at the right time

Both must be set up for EverMind to work as intended.

## Session Start Protocol

**At the beginning of every conversation, before any other work:**

### Step 1 — Load project context

Call `briefing()` or `briefing(fast=true)`.

- Returns memories (`memory_count > 0`) → read them, use as project context, proceed.
- Returns empty (`memory_count = 0`) → this is a new project, go to Step 2.

### Step 2 — New project: seed memory from codebase

When no memories exist yet, explore the repository first:

```
index_repository({"repo_path":"<absolute path>"})
get_architecture({"project":"<project-name>"})
```

Then save what you found:

```
remember("Tech stack: <languages, frameworks, databases>", importance=1, tags=["codebase-verified"], meta={"source":"codebase"})
remember("Entry point: <file> — run with <command>", importance=1, tags=["codebase-verified"], meta={"source":"codebase"})
remember("Build command: <cmd>  Test command: <cmd>", importance=1, tags=["codebase-verified"], meta={"source":"codebase"})
remember("Key modules: <summary>", importance=1, tags=["codebase-verified"], meta={"source":"codebase"})
```

## During Work

**Before starting any feature or bug investigation:**
```
recall("topic or component name")
```

Use `recall(..., min_score=0)` only when you intentionally want low-confidence diagnostic results.

**When you find something worth keeping:**
```
remember("content", importance=1)
```

For code facts, verify with `search_code`, `search_graph`, or `get_code_snippet` first, then add `tags=["codebase-verified"]` and `meta={"source":"codebase"}`. If `recall` or `graph_explore` returns `conflicts` or `forget_suggestions`, prefer verified codebase facts and ask before deleting old memory.

**When an existing memory is wrong or stale:**
```
update_memory({"id":"<memory-id>","content":"correct fact","tags":["codebase-verified"],"meta":{"source":"codebase"}})
```

Use `update_memory` for corrections that should keep the same memory ID. Use `forget` only when the memory should disappear entirely.

**For permanent decisions (architecture, critical bugs, permanent rules):**
```
remember("Decision: ...", importance=2)
```

## importance Values

| Value | Layer | Retention | Use for |
|-------|-------|-----------|---------|
| 0 | working | 24h auto-expire | Temporary scratch notes |
| 1 | episodic/semantic/procedural | Long-term | Project facts, events, workflows |
| 2 | archive | Permanent | Architecture decisions, never-delete rules |

## Auto Type Detection

Memory type is inferred from content automatically:
- "bug", "error", "fix", "crash" → episodic (bug event)
- "decided", "chose", "decision" → semantic (decision)
- "how to", "deploy", "steps", "procedure" → procedural
- "prefer", "always", "never" → preference

No need to set type manually.

## When to use codebase tools

Use alongside EverMind when:
- Starting work on an unfamiliar module
- Need to trace callers before refactoring
- Verifying change impact across files

```
search_code({"project":"<name>","pattern":"<symbol>"})
trace_path({"project":"<name>","function_name":"<fn>"})
```

## Safety

Never save API keys, tokens, passwords, private keys, or session credentials to memory.
