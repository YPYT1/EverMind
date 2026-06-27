# Components

EverMind is a fusion layer. It installs, configures, and checks the memory stack so users do not need to understand every upstream project before getting value.

## EverOS

EverOS is the local runtime for semantic memory, retrieval, indexing, and local storage. It owns the runtime data root configured by `EVEROS_ROOT`.

## evermemos MCP

The MCP bridge exposes memory tools to Codex, Claude Code, Cursor, Devin, and other MCP clients:

- `briefing`
- `recall`
- `remember`
- `propose_basic_memory_update`
- `commit_basic_memory_update`

## Basic Memory

Basic Memory is the reviewed Markdown archive layer. EverMind uses candidate-first writes by default:

1. generate a candidate;
2. user reviews;
3. official note is committed only after explicit confirmation.

Basic Memory is AGPL-3.0 and is installed as an external tool, not vendored into EverMind.

## codebase-memory-mcp

codebase-memory-mcp provides code graph indexing, architecture search, call-path tracing, snippet lookup, and change-impact analysis. EverMind installs the pinned release binary and keeps agent configuration under EverMind control.

codebase-memory-mcp is MIT licensed and remains an external component.

## EverMind Orchestration

EverMind coordinates:

- external component installation;
- unified `.env` and MCP snippets;
- memory routing;
- write policy;
- health checks;
- future local-to-cloud sync policy.

