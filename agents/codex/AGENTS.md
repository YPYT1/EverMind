# EverMind Agent Instructions — Codex

EverMind provides local 6-layer persistent memory via an embedded SQLite database.
No external service. No extra config. Memory survives across all sessions.

---

## Session Start Protocol

**Run at the beginning of every task, before any code changes.**

### Step 1 — Load memory

Call `briefing()`.

- Returns memories (`memory_count > 0`) → read context, proceed with task.
- Returns empty (`memory_count = 0`) → new project, go to Step 2.

### Step 2 — New project: explore and seed memory

When no memories exist, explore the repository first:

```
1. Index the repo:
   evermind-code-graph cli index_repository '{"repo_path":"<absolute path>"}'

2. Get architecture overview:
   evermind-code-graph cli get_architecture '{"project":"<project-name>"}'

3. Find entry points and config:
   evermind-code-graph cli search_graph '{"project":"<name>","query":"entry point config main"}'
```

Save key findings as the project's first memories:

```
remember("Tech stack: <languages, frameworks, databases>", importance=1)
remember("Entry point: <file> — run with <command>", importance=1)
remember("Build command: <command>  Test command: <command>", importance=1)
remember("Key modules: <brief summary>", importance=1)
```

---

## During Work

**Before starting a feature or investigating a bug:**
```
recall("topic or component name")
```

**After discovering something worth keeping:**
```
remember("content", importance=1)
```

**For permanent architecture decisions or critical bugs:**
```
remember("Decision: ...", importance=2)
```

**importance values:**
- `0` — working note, expires 24h (default)
- `1` — long-term memory
- `2` — permanent archive, never deleted

---

## Memory Layers

| Layer | Retention | Use for |
|-------|-----------|---------|
| working | 24h auto-expire | Temporary notes, WIP |
| episodic | Long-term | Events, bug fixes, discoveries |
| semantic | Long-term | Facts about the project |
| procedural | Long-term | Deploy steps, commands, workflows |
| archive | Permanent | Architecture decisions, permanent rules |

---

## codebase tools

Use `evermind-code-graph` when:
- Starting work on an unfamiliar module
- Checking callers of a function before refactoring
- Verifying cross-file impact

```
evermind-code-graph cli search_code '{"project":"<name>","pattern":"<symbol>"}'
evermind-code-graph cli trace_path '{"project":"<name>","function_name":"<fn>"}'
```

**Safety**: Never save API keys, tokens, passwords, or credentials.
