# EverMind Memory — Claude Code

EverMind provides local 6-layer persistent memory via an embedded SQLite database.
No external service. No extra config. Memory survives across all sessions automatically.

---

## Session Start Protocol

**Run this at the beginning of every conversation, before any other work.**

### Step 1 — Load memory

Call `briefing()`.

- If it returns memories: read them, use them as project context, proceed with the user's task.
- If it returns empty (memory_count = 0 or recent = []): this is a new project. Go to Step 2.

### Step 2 — New project: explore the codebase

When there are no memories yet, explore the repository to build initial context.

```
1. Index the repo (if not already indexed):
   evermind-code-graph cli index_repository '{"repo_path":"<absolute path to repo>"}'

2. Get architecture overview:
   evermind-code-graph cli get_architecture '{"project":"<project-name>"}'

3. Search for key entry points, config, and tech stack:
   evermind-code-graph cli search_graph '{"project":"<project-name>","query":"entry point main config"}'
```

After exploration, save what you found — these become the project's first memories:

```
remember("Tech stack: <what you found>", importance=1)
remember("Entry point: <main file and how to run>", importance=1)
remember("Build/test command: <command>", importance=1)
remember("Key modules: <summary of main modules>", importance=1)
```

This way the next session starts with real context instead of re-exploring from scratch.

---

## Memory Layers

| Layer | Retention | When to use |
|-------|-----------|-------------|
| working | 24h auto-expire | Temporary notes, WIP context |
| episodic | Long-term | Events, bug fixes, discoveries |
| semantic | Long-term | Facts about the project |
| procedural | Long-term | Deploy steps, build commands, workflows |
| archive | Permanent | Architecture decisions, permanent rules |

---

## During Work

**Before starting a feature or investigating a bug:**
```
recall("authentication flow")   ← search what's already known
```

**When you discover something useful:**
```
remember("Found that X causes Y when Z", importance=1)
```

**For permanent knowledge (architecture decisions, critical bugs):**
```
remember("Decision: use FastAPI over Flask because ...", importance=2)
```

**importance values:**
- `0` — working note, expires in 24h (default)
- `1` — long-term memory, persists indefinitely
- `2` — archive, never deleted

**Auto-detection:** memory type is inferred from content automatically.
- "bug", "error", "fix", "crash" → episodic
- "decided", "chose", "architecture" → semantic
- "how to", "steps", "deploy", "run" → procedural

---

## When to use codebase tools

Use `evermind-code-graph` when:
- Starting work on an unfamiliar module
- Need to check which files call a function before refactoring
- Verifying impact of a change across the codebase
- Memory says "see auth.py" but you need to confirm current state

```
evermind-code-graph cli search_code '{"project":"<name>","pattern":"<function name>"}'
evermind-code-graph cli trace_path '{"project":"<name>","function_name":"<function>"}'
```

---

## Safety

Never save API keys, tokens, passwords, private keys, or session credentials.
