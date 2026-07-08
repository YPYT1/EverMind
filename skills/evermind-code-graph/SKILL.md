---
name: evermind-code-graph
description: Use evermind-code-graph to inspect repository structure, architecture, call paths, snippets, and change impact before updating project memory.
---

## v2 Integration

Use alongside EverMind memory tools. Typical flow:
1. `briefing()` returns empty → index repo → `get_architecture` → `remember()` key facts
2. Starting work on unknown module → `search_graph` for context → `recall()` for prior decisions
3. Before broad refactor → `trace_path` for impact → `recall()` for past decisions about affected code

# Codebase Memory Skill

Use this skill when memory needs code evidence or when a repository is unfamiliar.

## Default Commands

```bash
evermind-code-graph cli list_projects '{}'
evermind-code-graph cli index_repository '{"repo_path":"<absolute-path>"}'
evermind-code-graph cli index_status '{"repo_path":"<absolute-path>"}'
evermind-code-graph cli get_architecture '{"project":"<project-name>"}'
evermind-code-graph cli search_graph '{"project":"<project-name>","query":"<keyword>"}'
evermind-code-graph cli search_code '{"project":"<project-name>","pattern":"<pattern>"}'
evermind-code-graph cli trace_path '{"project":"<project-name>","function_name":"<function>"}'
```

## Rules

- Use evermind-code-graph for discovery; verify important facts in real files.
- Prefer architecture and impact queries before broad refactors.
- Summarize stable conclusions into EverMind Archive only after validation.
