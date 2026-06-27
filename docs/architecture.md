# Architecture

EverMind is a local-first memory system for coding agents. Its architecture separates agent behavior, memory orchestration, and storage so each layer can evolve without forcing users to learn several independent tools.

## Three Layers

```text
Agent Layer
  Codex / Claude Code / Cursor / Devin
  EverMind skills
  agent instructions
  generated MCP config

Memory Orchestration Layer
  EverMind installer/checker
  EverMind MCP
  memory router
  write policy
  future cloud sync adapter

Storage Layer
  EverMind Runtime
  EverMind Archive
  EverMind Code Graph
  optional future cloud memory
```

## Agent Layer

The agent layer is where users experience EverMind. It includes:

- agent-specific instruction files under `agents/`;
- skills under `skills/`;
- generated MCP snippets under `generated/mcp-config/`;
- the agent's normal chat and coding workflow.

This layer tells the agent to:

1. read memory before significant work;
2. search memory when context is unclear;
3. write realtime memory only for useful facts;
4. create reviewed archive candidates after meaningful changes;
5. avoid storing secrets.

## Memory Orchestration Layer

The orchestration layer makes the system feel like one product:

- setup scripts create local directories, `.env`, skills, and MCP snippets;
- check scripts verify the runtime, MCP bridge, archive engine, code graph engine, model keys, and candidate directories;
- EverMind MCP exposes a stable set of memory tools;
- the write policy decides what can be stored automatically and what must be reviewed.

The main user-facing command is:

```text
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

## Storage Layer

EverMind uses different storage forms for different kinds of memory:

- realtime memory is optimized for quick recall and session restoration;
- archive memory is reviewed Markdown, suitable for stable project facts;
- code graph memory is optimized for repository structure, call paths, snippets, and impact analysis;
- future cloud memory is reserved as an adapter, not a v1 requirement.

## Memory Lifecycle

```text
briefing
  -> restore project/session context

recall
  -> search relevant prior memory

remember
  -> write realtime facts

propose_basic_memory_update
  -> create a reviewed archive candidate

commit_basic_memory_update
  -> write official archive notes only after explicit confirmation
```

This lifecycle prevents automatic realtime memory from becoming unreviewed project documentation.

## Why This Design

Simple memory systems often only provide one operation: store and retrieve text. That is useful, but insufficient for serious coding workflows. A coding agent also needs:

- a way to restore context before work starts;
- a way to inspect repository structure;
- a way to separate temporary session facts from long-term project knowledge;
- a write policy that blocks secrets;
- tool-specific configuration for real clients.

EverMind keeps those concerns in one repository while keeping the responsibilities separate.

