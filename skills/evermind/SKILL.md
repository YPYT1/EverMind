---
name: evermind
description: Core EverMind memory skill. Use at the start of every session and after meaningful work. Provides briefing, recall, remember, and forget operations via embedded SQLite. No external service required.
---

# EverMind Skill

EverMind gives AI coding agents persistent local memory across sessions.
It uses 4 MCP tools backed by an embedded SQLite database — no EverOS, no cloud, no API keys needed.

## Two-Component Architecture

EverMind has two parts that work together:

1. **MCP Server** — provides the 4 tools (remember / recall / forget / briefing)
2. **Skills** — shape agent behavior so the tools are used at the right time

Both must be set up for EverMind to work as intended.

## Session Start Protocol

**At the beginning of every conversation, before any other work:**

### Step 1 — Load project context

Call `briefing()`.

- Returns memories (`memory_count > 0`) → read them, use as project context, proceed.
- Returns empty (`memory_count = 0`) → this is a new project, go to Step 2.

### Step 2 — New project: seed memory from codebase

When no memories exist yet, explore the repository first:

```
evermind-code-graph cli index_repository '{"repo_path":"<absolute path>"}'
evermind-code-graph cli get_architecture '{"project":"<project-name>"}'
```

Then save what you found:

```
remember("Tech stack: <languages, frameworks, databases>", importance=1)
remember("Entry point: <file> — run with <command>", importance=1)
remember("Build command: <cmd>  Test command: <cmd>", importance=1)
remember("Key modules: <summary>", importance=1)
```

## During Work

**Before starting any feature or bug investigation:**
```
recall("topic or component name")
```

**When you find something worth keeping:**
```
remember("content", importance=1)
```

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

## When to use evermind-code-graph

Use alongside EverMind when:
- Starting work on an unfamiliar module
- Need to trace callers before refactoring
- Verifying change impact across files

```
evermind-code-graph cli search_code '{"project":"<name>","pattern":"<symbol>"}'
evermind-code-graph cli trace_path '{"project":"<name>","function_name":"<fn>"}'
```

## Safety

Never save API keys, tokens, passwords, private keys, or session credentials to memory.
