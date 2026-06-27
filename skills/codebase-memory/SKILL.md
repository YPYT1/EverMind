---
name: codebase-memory
description: Use codebase-memory to inspect repository structure, architecture, call paths, snippets, and change impact before updating project memory.
---

# Codebase Memory Skill

Use this skill when memory needs code evidence or when a repository is unfamiliar.

## Default Commands

```bash
codebase-memory-mcp cli list_projects '{}'
codebase-memory-mcp cli index_repository '{"repo_path":"<absolute-path>"}'
codebase-memory-mcp cli index_status '{"repo_path":"<absolute-path>"}'
codebase-memory-mcp cli get_architecture '{"project":"<project-name>"}'
codebase-memory-mcp cli search_graph '{"project":"<project-name>","query":"<keyword>"}'
codebase-memory-mcp cli search_code '{"project":"<project-name>","pattern":"<pattern>"}'
codebase-memory-mcp cli trace_path '{"project":"<project-name>","function_name":"<function>"}'
```

## Rules

- Use codebase-memory for discovery; verify important facts in real files.
- Prefer architecture and impact queries before broad refactors.
- Summarize stable conclusions into Basic Memory only after validation.

