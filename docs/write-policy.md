# Write Policy

EverMind v2 uses `remember()` with an `importance` parameter to create memories, and `update_memory()` to correct existing memories by ID. There is no separate propose/commit flow.

## Levels

### importance=0 — Working Memory (default)

Temporary notes that expire automatically after 24 hours.

Use for: current task context, WIP notes, scratch observations.

```
remember("Investigating the token refresh issue in auth.py", importance=0)
```

### importance=1 — Long-Term Memory

Persists indefinitely. Automatically classified into episodic, semantic, or procedural layer based on content.

Use for: project facts, bug discoveries, architecture notes, workflows.

```
remember("FastAPI handles async routes natively — no need for sync wrappers", importance=1)
```

### importance=2 — Archive (Permanent)

Never deleted. Goes into the archive layer regardless of content type.

Use for: architecture decisions, permanent rules, critical bug patterns.

```
remember("Decision: use PostgreSQL. Reason: concurrent writes failed with SQLite under load.", importance=2)
```

## What Not to Save

Never use `remember()` for:
- API keys, tokens, passwords, private keys, cookies, session credentials
- Personal data or PII
- Content that could change and become misleading (verify before saving)

## Correcting Existing Memories

Use `update_memory(id, content=...)` when a stored memory is wrong but should keep the same ID and history. Use `forget(id)` only when the memory should disappear entirely.

## Searching by Layer

Use `recall()` to retrieve memories. Results include a `layer` field:

```json
{"id": "...", "content": "...", "layer": "archive", "importance": 2}
```

To find permanent archive memories specifically, search with a relevant query — archive memories will rank higher due to their importance.
