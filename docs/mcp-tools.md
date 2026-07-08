# MCP Tools Reference

EverMind v2 provides 6 MCP tools. These are called by the AI agent automatically according to the session start protocol in the agent instruction files.

## briefing

**When to call**: At the start of every session, before any work.

**Returns**: Project context including recent memories, important memories, and total memory count.

```json
{
  "space": "coding:my-project",
  "memory_count": 12,
  "recent": [
    {"id": "...", "content": "...", "layer": "episodic", "importance": 1}
  ],
  "important": [
    {"id": "...", "content": "...", "layer": "archive", "importance": 2}
  ],
  "updated_at": 1720000000000
}
```

If `memory_count` is 0, this is a new project. The agent should explore the codebase using `evermind-code-graph` and seed initial memories.

**Parameters**: none

---

## remember

**When to call**: After discovering useful project facts, decisions, bugs, or workflows.

**Parameters**:
- `content` (string, required) — what to remember
- `importance` (0/1/2, default 0) — 0=working/24h, 1=long-term, 2=permanent archive
- `tags` (array of strings, optional) — for categorization
- `memory_type` (string, optional) — usually omitted; auto-detected from content

**Memory type auto-detection** (no need to set manually):
- content contains "bug", "error", "fix" → type: bug, layer: episodic
- content contains "decided", "decision" → type: decision, layer: semantic
- content contains "how to", "deploy", "steps" → type: procedural, layer: procedural
- content contains "prefer", "always", "never" → type: preference, layer: semantic
- default with importance ≥ 1 → type: semantic

**Returns**:
```json
{"id": "uuid", "action": "stored", "layer": "episodic", "type": "bug", "similar_merged": false}
```

If identical content was already stored, returns `"action": "merged"` and does not create a duplicate.

---

## recall

**When to call**: Before starting work on a feature or bug; when uncertain about a prior decision.

**Parameters**:
- `query` (string, required) — what to search for
- `limit` (integer, default 10) — max results
- `mode` ("hybrid"/"fts"/"semantic", default "hybrid") — search strategy

**Search modes**:
- `hybrid` — BM25 keyword + vector KNN fused with RRF (best results, requires sqlite-vec)
- `fts` — keyword-only BM25 (works without optional deps)
- `semantic` — vector-only (requires sqlite-vec)

**Returns**:
```json
{
  "results": [
    {"id": "...", "content": "...", "layer": "semantic", "score": 0.84}
  ],
  "mode": "hybrid",
  "count": 3,
  "query": "authentication"
}
```

---

## forget

**When to call**: When a memory is outdated or incorrect and should not appear in future recalls.

**Parameters**:
- `id` (string, required) — the memory ID from a previous `recall()` result

**Returns**:
```json
{"deleted": true, "id": "uuid"}
```

---

## list

**When to call**: When you need to browse memories by layer or tag rather than search by query.

**Parameters**:
- `layer` (string, optional) — filter by layer name: `working`, `episodic`, `semantic`, `procedural`, `archive`, `graph`
- `tags` (array of strings, optional) — filter by one or more tags
- `limit` (integer, default 20) — max results to return

**Returns**:
```json
{
  "results": [
    {"id": "...", "content": "...", "layer": "semantic", "tags": ["auth"], "importance": 1}
  ],
  "count": 5
}
```

---

## graph_explore

**When to call**: When you want to find memories related to a specific entity (e.g. a module, function, concept, or person).

**Parameters**:
- `entity` (string, required) — the entity name to look up in the knowledge graph

**Returns**:
```json
{"entity": "AuthService", "related_memories": [{"id": "...", "content": "...", "layer": "semantic"}], "count": 3}
```

---

## Memory Layers

| Layer | Importance | Retention | Typical content |
|-------|-----------|-----------|-----------------|
| working | 0 | 24h auto-expire | Temporary notes |
| episodic | 1 | Long-term | Bug fixes, events |
| semantic | 1 | Long-term | Project facts, decisions |
| procedural | 1 | Long-term | Workflows, commands |
| archive | 2 | Permanent | Architecture decisions |
| graph | — | Permanent | Entity relationships (Phase 3) |
