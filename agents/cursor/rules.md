# EverMind Memory — Cursor

EverMind provides local 6-layer persistent memory via an embedded SQLite database.
No external service. No extra config. Memory survives across all sessions.

---

## Session Start Protocol

**At the start of every conversation, before any other work:**

### Step 1 — Load memory
Call briefing().

- Returns memories (memory_count > 0) → read them, proceed.
- Returns empty (memory_count = 0) → new project, go to Step 2.

### Step 2 — New project: explore the codebase

```
evermind-code-graph cli index_repository '{"repo_path":"<absolute path>"}'
evermind-code-graph cli get_architecture '{"project":"<project-name>"}'
evermind-code-graph cli search_graph '{"project":"<name>","query":"entry point config main"}'
```

Then save findings:
```
remember("Tech stack: ...", importance=1)
remember("Entry point: ...", importance=1)
remember("Build/test commands: ...", importance=1)
```

---

## During Work

Before any feature or bug investigation:
```
recall("topic or component name")
```

After finding something useful:
```
remember("content", importance=1)
```

For permanent decisions:
```
remember("Architecture decision: ...", importance=2)
```

importance values:
- 0 — working note, expires 24h (default)
- 1 — long-term memory
- 2 — permanent archive (never deleted)

---

## Memory Layers

| Layer | Retention | Use for |
|-------|-----------|---------|
| working | 24h | Temporary notes |
| episodic | Long-term | Events, bug fixes |
| semantic | Long-term | Project facts, decisions |
| procedural | Long-term | Deploy steps, workflows |
| archive | Permanent | Architecture decisions |

---

## Codebase Tools

Use evermind-code-graph for unfamiliar code or before large changes.

**search_graph** — traverse the knowledge graph (modules, functions, call paths):
```
evermind-code-graph cli search_graph '{"project":"<name>","query":"<concept>"}'
evermind-code-graph cli trace_path '{"project":"<name>","function_name":"<fn>"}'
```

**search_code** — text/pattern search in source files (like grep):
```
evermind-code-graph cli search_code '{"project":"<name>","pattern":"<symbol>"}'
```

Use search_graph to understand architecture and relationships.
Use search_code to find a specific function, class, or pattern in the source.

---

## Skills

Load EverMind skills in your project's .cursorrules or Cursor rules file:

Available skills (reference by full path):
- skills/evermind/SKILL.md — core memory workflow (load in every project)
- skills/evermind-archive/SKILL.md — writing permanent memories
- skills/evermind-code-graph/SKILL.md — codebase exploration
- skills/project-memory/SKILL.md — first-time project initialization

---

## Safety

Never save API keys, tokens, passwords, private keys, or credentials.
