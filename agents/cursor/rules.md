# EverMind Memory — Cursor

EverMind provides local 6-layer persistent memory via an embedded SQLite database.
No extra config. Memory survives across all sessions automatically.

---

## Session Start Protocol

**At the start of every conversation:**

### Step 1 — Load memory
Call `briefing()`.

- Returns memories → use as project context, proceed.
- Returns empty (memory_count = 0) → new project, go to Step 2.

### Step 2 — New project: explore the codebase

```
evermind-code-graph cli index_repository '{"repo_path":"<absolute path>"}'
evermind-code-graph cli get_architecture '{"project":"<project-name>"}'
```

Then save findings:
```
remember("Tech stack: ...", importance=1)
remember("Entry point: ...", importance=1)
remember("Build/test command: ...", importance=1)
```

---

## During Work

- Before a feature or bug investigation: `recall("relevant topic")`
- After discovering something useful: `remember(content, importance=1)`
- Architecture decisions, permanent rules: `remember(content, importance=2)`
- `importance=0` = working note, expires 24h (default)

---

## Memory Layers

| Layer | Retention | Use for |
|-------|-----------|---------|
| working | 24h | Temporary notes |
| episodic | Long-term | Events, bug fixes |
| semantic | Long-term | Project facts |
| procedural | Long-term | Deploy steps, workflows |
| archive | Permanent | Architecture decisions |

**Safety**: Never save API keys, tokens, passwords, or credentials.
