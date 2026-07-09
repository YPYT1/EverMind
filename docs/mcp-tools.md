# MCP Tools Reference

EverMind v2 exposes one unified MCP server with 42 tools: 14 memory tools, 14 Codebase Memory graph tools, and 14 Basic Memory archive tools. Agents only need the `evermind` MCP entry.

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

If `memory_count` is 0, this is a new project. The agent should use the built-in codebase tools (`index_repository`, `get_architecture`, `search_code`, `search_graph`) and seed initial memories.

**Parameters**:
- `fast` (boolean, default true) — skip synchronous LLM summary and return cached structured context immediately

---

## remember

**When to call**: After discovering useful project facts, decisions, bugs, or workflows.

**Parameters**:
- `content` (string, required) — what to remember
- `importance` (0/1/2, default 0) — 0=working/24h, 1=long-term, 2=permanent archive
- `tags` (array of strings, optional) — for categorization
- `memory_type` (string, optional) — usually omitted; auto-detected from content
- `meta` (object, optional) — use `{"source":"codebase","verified_at":"..."}` for codebase-verified facts

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

For facts extracted from codebase tools, add `tags=["codebase-verified"]` and `meta.source="codebase"`. Verified negative facts such as "auth.ts does not exist" are prioritized over older unverified positive memories and may produce `forget_suggestions`.

---

## update_memory

**When to call**: When an existing memory is wrong or stale but should keep the same ID/history.

**Parameters**:
- `id` (string, required) — memory ID from `recall`, `list`, `graph_explore`, or `briefing`
- `content` (string, optional) — replacement content
- `importance` (0/1/2, optional) — recalculates layer
- `tags` (array of strings, optional) — replacement tag list
- `memory_type` (string, optional) — set `auto` to re-detect from content
- `meta` (object, optional) — replacement metadata such as `{"source":"codebase"}`

**Returns**:
```json
{"updated": true, "id": "uuid", "action": "updated", "layer": "archive", "type": "decision"}
```

The update path rebuilds FTS, refreshes embeddings, replaces graph links when content changes, and refreshes briefing cache. Use this for correcting hallucinated facts such as `auth.ts` instead of `forget` + `remember`.

---

## recall

**When to call**: Before starting work on a feature or bug; when uncertain about a prior decision.

**Parameters**:
- `query` (string, required) — what to search for
- `limit` (integer, default 10) — max results
- `mode` ("hybrid"/"fts"/"semantic", default "hybrid") — search strategy
- `layer` (string, optional) — filter by memory layer
- `tags` (array of strings, optional) — filter by tags
- `space` (string, optional) — override current project space
- `all_spaces` (boolean, default false) — search across all spaces
- `min_score` (number, default 0.15) — final relevance threshold; set 0 to inspect all ranked candidates

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
  "query": "authentication",
  "conflicts": [],
  "forget_suggestions": []
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
{"entity": "AuthService", "related_memories": [{"id": "...", "content": "...", "layer": "semantic"}], "count": 3, "conflicts": []}
```

---

## status

**When to call**: When debugging memory counts, embedding/FTS coverage, model availability, or recall latency.

**Parameters**: none

---

## health

**When to call**: When diagnosing duplicate memories, expired working memories, embedding queue state, or API failure counts.

**Parameters**: none

---

## export

**When to call**: When auditing memories or generating documentation from stored knowledge.

**Parameters**:
- `layer` (string, optional) — export only one layer
- `format` ("markdown"/"json", default "markdown") — output format

---

## compact

**When to call**: When old episodic memories should be compacted into a semantic summary.

**Parameters**:
- `older_than_days` (integer, default 30) — compact episodic memories older than this many days

---

## tags

**When to call**: Before filtering `recall()` or `list()` by tags.

**Parameters**: none

---

## reindex

**When to call**: After installing jieba, changing tokenization, or when keyword search misses known memories.

**Parameters**:
- `all_spaces` (boolean, default false) — rebuild indexes for all spaces

---

## list_spaces

**When to call**: When inspecting known project spaces or debugging `all_spaces` behavior.

**Parameters**: none

---

## Codebase Memory Tools

These tools are exposed by EverMind but executed by the bundled `codebase-memory-mcp` engine:

`index_repository`, `list_projects`, `delete_project`, `index_status`, `search_graph`, `trace_path`, `detect_changes`, `query_graph`, `get_graph_schema`, `get_code_snippet`, `get_architecture`, `search_code`, `manage_adr`, `ingest_traces`.

Use them before writing project facts into memory. Stable code facts should be saved with `tags=["codebase-verified"]`.

---

## Basic Memory Archive Tools

These tools are exposed by EverMind but executed through the installed Basic Memory CLI:

`write_note`, `read_note`, `delete_note`, `edit_note`, `build_context`, `recent_activity`, `search_notes`, `list_memory_projects`, `list_workspaces`, `schema_validate`, `schema_infer`, `schema_diff`, `propose_basic_memory_update`, `commit_basic_memory_update`.

`propose_basic_memory_update` writes a candidate only. `commit_basic_memory_update` requires `confirmed=true`.

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
