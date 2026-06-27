# Architecture

EverMind is an integrated local-first memory system for coding agents.

```text
Agent Layer
  Codex / Claude Code / Cursor / Devin
  skills + agent rules + unified MCP config

Memory Orchestration Layer
  EverMind installer/checker
  evermemos MCP bridge
  Basic Memory adapter
  codebase-memory adapter
  memory router
  write policy
  future cloud sync adapter

Storage Layer
  EverOS local runtime
  Basic Memory reviewed Markdown archive
  codebase-memory local graph index
  optional future cloud memory
```

## Components

- EverOS: local semantic memory runtime and retrieval API.
- evermemos MCP: tool bridge for agents.
- Basic Memory: reviewed Markdown project archive.
- codebase-memory-mcp: code graph indexing, architecture search, call paths, and impact analysis.
- Skills and agent templates: behavior instructions for reading, searching, and writing memory.

EverMind owns orchestration, installation, configuration, and health checks. It does not vendor upstream Basic Memory or codebase-memory-mcp source code.

