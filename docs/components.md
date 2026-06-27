# Components

EverMind is presented as one local-first memory system with four user-facing components.

## EverMind Runtime

EverMind Runtime is the local realtime memory backend. It owns fast project and session recall, local memory files, indexes, and runtime state.

In the local-first edition this runtime is EverOS-compatible, so existing EverOS deployments can be used as the storage and retrieval engine behind EverMind Runtime.

Use it for:

- session context;
- project facts that help future recall;
- user preferences;
- memory search before and during coding work.

## EverMind MCP

EverMind MCP is the bridge between agents and memory. It lives directly under `mcp/` and exposes the memory tools used by Codex, Claude Code, Cursor, Devin, and other MCP clients.

It is started with:

```text
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

Use it for:

- `briefing`;
- `recall`;
- `remember`;
- archive candidate creation;
- official archive commit after explicit confirmation.

## EverMind Archive

EverMind Archive is the reviewed long-term project knowledge layer. It stores durable facts as Markdown so users can read, diff, edit, and back up the knowledge base without a special UI.

Use it for:

- architecture decisions;
- module responsibilities;
- runtime configuration;
- interface contracts;
- test and verification practices;
- known pitfalls;
- modification history.

EverMind uses candidate-first writes by default so agents cannot silently pollute official notes.

## EverMind Code Graph

EverMind Code Graph indexes repositories for code-aware memory tasks.

Use it for:

- architecture search;
- call-path tracing;
- code search;
- snippet lookup;
- change-impact analysis.

The stable conclusions from code graph analysis should be written into EverMind Archive only when they are useful for future work.

## Compliance Boundary

EverMind owns orchestration, installation, configuration, health checks, skills, agent templates, and the branded user experience.

Third-party source, version, and license details are centralized in `THIRD_PARTY_NOTICES.md` and `third_party.lock.yaml`. This keeps the main user path clean while preserving open-source compliance.

