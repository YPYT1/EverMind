# Changelog

## [2.0.0] — 2026-07-08

### Overview

Complete rewrite of the EverMind MCP layer. Replaced the EverOS HTTP dependency
with an embedded SQLite database. Reduced 9 MCP tools to 4. Zero-config setup.

### Breaking Changes

- Minimum configuration is now zero — no environment variables required for basic use.
- Entry point changed to `evermind_mcp.server_v2:main_sync`.
- Old `space_id` parameter removed from tools; project space is auto-detected from git remote.
- `propose_archive_update` and `commit_archive_update` removed; use `remember(importance=2)` instead.

### New Features

- **Embedded storage**: SQLite + FTS5 + optional sqlite-vec. No external process required.
- **6-layer memory model**: working (24h) / episodic / semantic / procedural / archive / graph.
- **Auto type detection**: content keywords automatically classify memories as bug/decision/procedural/preference.
- **Exact + fuzzy deduplication**: identical content merged on write; BM25 similarity for near-duplicates.
- **Hybrid search**: BM25 (FTS5) + vector KNN (sqlite-vec) fused with RRF when both are available.
- **Pre-materialized briefing cache**: session start context loads in <5ms.
- **Single install command**: `uv sync --extra full` installs all optional dependencies.
- **Setup scripts**: `scripts/setup-windows.ps1` and `scripts/setup-macos.sh` with auto-config for Claude Desktop and Cursor.
- **Session start protocol**: CLAUDE.md/AGENTS.md updated with `briefing()` → codebase exploration fallback for new projects.

### Performance

| Operation | v1 | v2 |
|-----------|----|----|
| remember() | 200ms–5s | <20ms |
| recall() | 300ms–3s | <30ms |
| briefing() | 500ms–1s | <5ms |
| Config vars needed | 20+ | 0 |

### Removed

- `EverOS` dependency (external HTTP service on port 3378)
- Legacy HTTP/cloud modules such as `server.py`, `memory_service.py`,
  `everos_client.py`, `cloud_client.py`, `space_catalog_service.py`,
  `content_guard.py`, and `config.py` (replaced by v2 equivalents)
- Runtime bridge requirements for code graph and archive engines; both now run
  through in-repo source-fused backends with local fallback behavior.

---

## [0.5.6] and earlier

See git history for previous changelog entries.
