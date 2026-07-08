---
name: evermind-archive
description: Use for saving permanent, long-term project knowledge to EverMind. In v2, permanent knowledge is saved with remember(importance=2) — no separate propose/commit flow required.
---

# EverMind Archive Skill

In EverMind v2, "archive" is a memory layer — not a separate file system.

Use `remember(content, importance=2)` to save permanent project knowledge directly.
It goes into the archive layer immediately, never expires, and survives all sessions.

## What belongs in the archive layer

Save with `importance=2` when the information is:

- An architecture decision and its rationale
- A critical bug that was hard to find, and its fix
- A permanent rule or convention for this codebase
- A deployment or release procedure that rarely changes
- A known dangerous area that future agents must not touch

## What does NOT belong in archive

- Temporary task notes → use `importance=0` (expires in 24h)
- Regular project facts → use `importance=1` (long-term but not permanent)
- API keys, tokens, credentials → never store these

## Format

When writing archive memories, be specific:

```
remember(
  "Decision: use PostgreSQL over SQLite for multi-user writes. "
  "Reason: concurrent write locks caused failures in load testing (2026-07-01). "
  "Verified: see tests/load/concurrent_write_test.py",
  importance=2
)
```

Include: what, why, evidence reference, and date if relevant.

## Searching archive memories

```
recall("architecture decision postgres")
recall("known bug auth module")
```

Results include a `layer` field — archive memories show `"layer": "archive"`.
