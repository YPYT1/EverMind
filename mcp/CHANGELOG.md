# Changelog

## [2.0.0]

- Shipped the 50-tool unified EverMind MCP v2 interface with local memory, code graph, vendored Basic Memory, reviewed archive updates, and one project lifecycle.
- Added `update_memory` for direct correction of wrong or stale memories while rebuilding FTS, embeddings, graph links, and briefing cache.
- Added SiliconFlow-backed Qwen/Qwen3-Embedding-8B embeddings, Qwen/Qwen3-Reranker-8B reranking, and optional DeepSeek briefing summaries.
- Added production observability for external API failures, p50/p95 latency, rerank fallback reasons, recall traces, embedding coverage, and graph health.
- Strengthened graph extraction for paths, technical concepts, Chinese workflow terms, and graph reindex recovery.
- Added sensitive-memory rejection and reindex/health/list_spaces operational tools.

## [0.5.6]

- Rebranded the bundled MCP interface as EverMind MCP.
- Kept the 9-tool local memory workflow.
- Preserved compatibility fallback for legacy environment variables.
- Tightened public configuration around `EVERMIND_MCP_*`.
