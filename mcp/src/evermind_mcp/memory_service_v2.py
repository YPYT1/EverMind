"""
EverMind Memory Service v2

Replaces the old 2876-line memory_service.py with a clean, modular implementation
that delegates storage, embedding, and type concerns to dedicated modules.
"""

import logging
import threading
import time
from collections import deque

from .storage import EmbeddedStorage
from .embedding import EmbeddingManager
from .reranker import RerankerManager
from .llm import LLMManager
from .config_v2 import EverMindConfig
from .content_guard import scan_sensitive_content

logger = logging.getLogger(__name__)

# Layer assignment constants
LAYER_ARCHIVE = "archive"
LAYER_EPISODIC = "episodic"
LAYER_WORKING = "working"
LAYER_SEMANTIC = "semantic"
LAYER_PROCEDURAL = "procedural"

# Memory type constants
TYPE_BUG = "bug"
TYPE_PROCEDURAL = "procedural"
TYPE_DECISION = "decision"
TYPE_PREFERENCE = "preference"
TYPE_SEMANTIC = "semantic"
TYPE_EPISODIC = "episodic"

# Briefing cache TTL in milliseconds (5 minutes)
BRIEFING_CACHE_TTL_MS = 300_000

# RRF fusion constant
RRF_K = 60

# Dedup similarity threshold
DEDUP_THRESHOLD = 0.3
DEDUP_MERGE_THRESHOLD = 0.5


def _detect_memory_type(content: str, importance: int) -> str:
    """Auto-detect memory type from content keywords."""
    lower = content.lower()

    if any(k in lower for k in ("bug", "error", "fix", "crash", "exception")):
        return TYPE_BUG

    if any(k in lower for k in ("how to", "步骤", "流程", "procedure", "deploy", "run", "如何", "方法", "命令", "运行", "执行")):
        return TYPE_PROCEDURAL

    if any(k in lower for k in ("decided", "decision", "chose", "选择", "决定")):
        return TYPE_DECISION

    if any(k in lower for k in ("prefer", "always", "never", "喜欢", "偏好")):
        return TYPE_PREFERENCE

    if importance >= 1:
        return TYPE_SEMANTIC

    return TYPE_EPISODIC


def _assign_layer(importance: int, memory_type: str) -> str:
    """Assign storage layer based on importance and memory type.

    importance=2 is always archive regardless of type.
    importance=1 is routed by type; defaults to episodic.
    importance=0 is working (24h expiry).
    """
    if importance == 2:
        return LAYER_ARCHIVE

    if memory_type == TYPE_PROCEDURAL:
        return LAYER_PROCEDURAL

    if memory_type in (TYPE_SEMANTIC, TYPE_DECISION, TYPE_PREFERENCE):
        return LAYER_SEMANTIC

    if importance == 1:
        return LAYER_EPISODIC

    return LAYER_WORKING


def _rrf_score(rank_fts: int, rank_vec: int) -> float:
    """Compute Reciprocal Rank Fusion score."""
    return 1.0 / (RRF_K + rank_fts) + 1.0 / (RRF_K + rank_vec)


class MemoryService:
    """
    Core memory service for EverMind v2.

    Orchestrates storage, embedding, deduplication, retrieval fusion,
    and briefing cache management.
    """

    def __init__(self, config: EverMindConfig) -> None:
        self.config = config
        self.storage = EmbeddedStorage(config.db_path(config.default_space))
        self.embedder = EmbeddingManager(
            model_name=config.embed_model,
            enabled=config.embed_enabled,
            provider=config.embed_provider,
            api_key=config.siliconflow_api_key,
            api_base_url=config.siliconflow_base_url,
            dimensions=config.embed_dim,
            timeout_seconds=config.api_timeout_seconds,
            queue_max_retries=config.embed_queue_max_retries,
        )
        self.embedder.set_callback(self._on_embedding_ready)
        self.reranker = RerankerManager(
            model_name=config.rerank_model,
            enabled=config.rerank_enabled,
            api_key=config.siliconflow_api_key,
            api_base_url=config.siliconflow_base_url,
            timeout_seconds=config.api_timeout_seconds,
            instruction=config.rerank_instruction,
        )
        self.llm = LLMManager(
            model_name=config.llm_model,
            enabled=config.llm_enabled,
            api_key=config.siliconflow_api_key,
            api_base_url=config.siliconflow_base_url,
            timeout_seconds=config.api_timeout_seconds,
        )
        self.space = config.default_space
        self._last_recall_latency_ms: float | None = None
        self._recall_latencies: deque[float] = deque(maxlen=200)
        self._last_recall_trace: dict = {}

        # CHANGE 6: Check embedding dimension matches storage expectation
        if self.embedder.available:
            actual_dim = self.embedder.dim
            if not self.storage.check_embed_dim(actual_dim):
                logger.warning("Vector search disabled due to embedding dimension mismatch.")
                self.embedder._enabled = False

        if config.auto_reindex_on_start:
            try:
                self.storage.reindex_fts(self.space)
            except Exception as exc:
                logger.debug("Auto reindex failed: %s", exc)

        if config.embed_warmup_on_start and self.embedder.available:
            self.embedder.warmup()
        if self.reranker.available:
            self.reranker.warmup()

        # Single persistent briefing worker (replaces per-call thread spawning)
        self._briefing_event = threading.Event()
        self._briefing_worker = threading.Thread(
            target=self._briefing_worker_loop,
            daemon=True,
            name="evermind-briefing",
        )
        self._briefing_worker.start()

    def set_space(self, space: str) -> None:
        """Switch the active project space and backing SQLite database."""
        if not space or space == self.space:
            return
        self.storage.close_all()
        self.storage = EmbeddedStorage(self.config.db_path(space))
        self.space = space
        if self.embedder.available:
            actual_dim = self.embedder.dim
            if not self.storage.check_embed_dim(actual_dim):
                logger.warning("Vector search disabled due to embedding dimension mismatch.")
                self.embedder._enabled = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def remember(
        self,
        content: str,
        importance: int = 0,
        tags: list = [],
        memory_type: str = "auto",
        role: str = "user",
    ) -> dict:
        """
        Store a memory, with automatic type detection, layer assignment,
        and near-duplicate merging.
        """
        space = self.space

        if self.config.sensitive_memory_block:
            sensitive_matches = scan_sensitive_content(content)
            if sensitive_matches:
                self.storage.log_event(
                    space,
                    "remember_rejected",
                    None,
                    {
                        "reason": "sensitive_content",
                        "categories": sorted({m.category for m in sensitive_matches}),
                    },
                )
                return {
                    "action": "rejected",
                    "error": "sensitive_content",
                    "sensitive_matches": [
                        {
                            "category": m.category,
                            "matched_text": m.matched_text,
                            "description": m.description,
                        }
                        for m in sensitive_matches
                    ],
                }

        # Auto-detect type if not explicitly set
        if memory_type == "auto":
            memory_type = _detect_memory_type(content, importance)

        layer = _assign_layer(importance, memory_type)

        # Dedup: exact match first (catches identical content regardless of BM25 score)
        exact = self.storage.find_exact(content, space)
        if exact is not None:
            self.storage.log_event(space, "remember_merged", exact.id, {"reason": "exact_match"})
            return {
                "id": exact.id,
                "action": "merged",
                "layer": exact.layer,
                "type": exact.memory_type,
                "similar_merged": True,
            }

        # Cosine dedup: merge near-duplicates above threshold
        if self.embedder.available and self.config.cosine_dedup_threshold > 0:
            new_vec = self.embedder.encode(content)
            if new_vec is not None:
                similar_vecs = self.storage.search_vec(new_vec, space, limit=3)
                for candidate in similar_vecs:
                    cand_vec = self.embedder.encode(candidate.content)
                    if cand_vec is not None:
                        sim = self.embedder.cosine_similarity(new_vec, cand_vec)
                        if sim >= self.config.cosine_dedup_threshold:
                            self.storage.update_memory_content(candidate.id, content)
                            if self.config.graph_enabled:
                                entities = self.storage.extract_entities_from_content(content)
                                if entities:
                                    self.storage.link_memory_to_entities(
                                        candidate.id,
                                        space,
                                        entities,
                                    )
                            self.storage.log_event(space, "remember_merged", candidate.id, {"reason": "cosine_similarity", "score": round(sim, 4)})
                            return {"id": candidate.id, "action": "merged", "layer": candidate.layer, "type": candidate.memory_type, "similar_merged": True, "similarity": round(sim, 4)}

        # Insert new memory
        memory = self.storage.insert_memory(
            content=content,
            space=space,
            layer=layer,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            role=role,
        )

        # Enqueue background embedding
        self.embedder.enqueue(memory.id, content)

        # Log the event
        self.storage.log_event(space, "remember", memory.id, {"importance": importance})

        # CHANGE 4: Graph integration - link entities after insert
        if self.config.graph_enabled:
            entities = self.storage.extract_entities_from_content(content)
            if entities:
                self.storage.link_memory_to_entities(memory.id, space, entities)
                logger.debug("Graph: linked %d entities to memory %s", len(entities), memory.id)

        # Trigger briefing refresh in background if important enough
        if importance >= 1:
            self._signal_briefing_refresh()

        logger.debug("Memory stored id=%s layer=%s type=%s", memory.id, layer, memory_type)
        return {
            "id": memory.id,
            "action": "stored",
            "layer": layer,
            "type": memory_type,
            "similar_merged": False,
        }

    async def recall(
        self,
        query: str,
        limit: int = 10,
        mode: str = "hybrid",
        space: str = None,
        layer: str = None,
        tags: list = None,
        all_spaces: bool = False,
    ) -> dict:
        """
        Retrieve memories matching a query using FTS, semantic search,
        hybrid RRF fusion, and optional cross-encoder reranking.
        """
        started = time.perf_counter()
        if space is None:
            space = self.space

        candidate_limit = max(
            limit * 2,
            self.config.rerank_candidates if self.reranker.available else limit * 2,
        )

        # All-spaces search: search across all known spaces using multi-space FTS
        if all_spaces:
            known_spaces = self.storage.list_spaces()
            fts_results = self.storage.search_fts_multi(query, known_spaces, limit=candidate_limit)
            mode_used = "fts"
            final_list, rerank_applied, rerank_fallback = self._rerank_if_available(
                query,
                fts_results,
                limit,
            )
            if rerank_applied:
                mode_used = "fts+rerank"
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            self._record_recall_trace(
                space,
                query,
                mode,
                mode_used,
                len(fts_results),
                0,
                len(final_list),
                rerank_applied,
                rerank_fallback,
                latency_ms,
                all_spaces=True,
            )
            return {
                "results": [m.to_dict() for m in final_list],
                "mode": mode_used,
                "count": len(final_list),
                "query": query,
                "all_spaces": True,
                "latency_ms": latency_ms,
                "rerank_applied": rerank_applied,
                "rerank_fallback_reason": rerank_fallback,
            }

        # Quick working-memory expiry
        self.storage.expire_working_memories(space)

        # Log the recall event
        self.storage.log_event(space, "recall", None, {"query": query[:100]})

        fts_results: list = []
        vec_results: list = []

        # Full-text search
        if mode in ("hybrid", "fts"):
            fts_results = self.storage.search_fts(query, space, limit=candidate_limit, layer=layer, tags=tags)

        # Semantic / vector search
        if mode in ("hybrid", "semantic"):
            vec = self.embedder.encode(query)
            if vec is not None:
                vec_results = self.storage.search_vec(vec, space, limit=candidate_limit)
                if layer:
                    vec_results = [r for r in vec_results if r.layer == layer]
                if tags:
                    wanted = set(tags)
                    vec_results = [r for r in vec_results if wanted.intersection(set(r.tags))]

        # Fuse results
        if fts_results and vec_results:
            # Build rank lookup: id -> rank index (0-based)
            fts_rank = {r.id: idx for idx, r in enumerate(fts_results)}
            vec_rank = {r.id: idx for idx, r in enumerate(vec_results)}

            # Union of all ids
            all_ids: set = set(fts_rank) | set(vec_rank)

            # Score each id
            scored = []
            id_to_memory: dict = {r.id: r for r in fts_results}
            id_to_memory.update({r.id: r for r in vec_results})

            for mid in all_ids:
                rf = fts_rank.get(mid, 9999)
                rv = vec_rank.get(mid, 9999)
                score = _rrf_score(rf, rv)
                id_to_memory[mid].score = score
                scored.append((score, mid))

            scored.sort(key=lambda x: x[0], reverse=True)
            final_list = [id_to_memory[mid] for _, mid in scored[:candidate_limit]]
            mode_used = "hybrid"

        elif fts_results:
            final_list = fts_results[:candidate_limit]
            mode_used = "fts"

        elif vec_results:
            final_list = vec_results[:candidate_limit]
            mode_used = "semantic"

        else:
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            self._record_recall_trace(
                space,
                query,
                mode,
                mode,
                len(fts_results),
                len(vec_results),
                0,
                False,
                "no_candidates",
                latency_ms,
            )
            return {
                "results": [],
                "mode": mode,
                "count": 0,
                "query": query,
                "latency_ms": latency_ms,
                "rerank_applied": False,
                "rerank_fallback_reason": "no_candidates",
            }

        final_list, rerank_applied, rerank_fallback = self._rerank_if_available(
            query,
            final_list,
            limit,
        )
        if not rerank_applied:
            final_list = final_list[:limit]
        else:
            mode_used = f"{mode_used}+rerank"

        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        self._record_recall_trace(
            space,
            query,
            mode,
            mode_used,
            len(fts_results),
            len(vec_results),
            len(final_list),
            rerank_applied,
            rerank_fallback,
            latency_ms,
        )
        return {
            "results": [m.to_dict() for m in final_list],
            "mode": mode_used,
            "count": len(final_list),
            "query": query,
            "latency_ms": latency_ms,
            "rerank_applied": rerank_applied,
            "rerank_fallback_reason": rerank_fallback,
            "fts_candidates": len(fts_results),
            "vec_candidates": len(vec_results),
        }

    async def list_memories(
        self,
        layer: str = None,
        tags: list = None,
        limit: int = 20,
    ) -> dict:
        """List memories with optional layer and tags filter."""
        space = self.space
        self.storage.expire_working_memories(space)
        memories = self.storage.list_memories(space, layer=layer, tags=tags, limit=limit)
        return {
            "memories": [m.to_dict() for m in memories],
            "count": len(memories),
            "filter": {"layer": layer, "tags": tags},
        }

    async def forget(self, memory_id: str) -> dict:
        """Permanently delete a memory by ID."""
        deleted = self.storage.delete_memory(memory_id)
        if deleted:
            self.storage.log_event(self.space, "forget", memory_id, {})
            self._signal_briefing_refresh()
            return {"deleted": True, "id": memory_id}
        return {"deleted": False, "id": memory_id, "error": "not found"}

    async def briefing(self) -> dict:
        """
        Return a structured briefing of the current memory state.
        Uses a 5-minute cache; refreshes when stale.
        """
        self.storage.expire_working_memories(self.space)

        cache = self.storage.get_briefing_cache(self.space)
        now_ms = int(time.time() * 1000)

        if cache is None or (now_ms - cache.updated_at) > BRIEFING_CACHE_TTL_MS:
            cache = self.storage.refresh_briefing_cache(
                self.space,
                recent_limit=self.config.briefing_recent,
                important_limit=self.config.briefing_important,
            )

        data = cache.to_dict()
        memories_for_summary = data.get("important", []) + data.get("recent", [])
        if self.config.llm_briefing_summary:
            summary = self.llm.summarize_briefing(memories_for_summary)
            if summary:
                data["context_summary"] = summary
        data["warnings"] = [
            m for m in memories_for_summary
            if (m.get("memory_type") or m.get("type")) == TYPE_BUG
        ][:5]
        data["decisions"] = [
            m for m in memories_for_summary
            if m.get("layer") == LAYER_ARCHIVE or (m.get("memory_type") or m.get("type")) == TYPE_DECISION
        ][:5]
        return data

    async def graph_explore(self, entity: str) -> dict:
        """Explore graph relationships for a given entity."""
        space = self.space
        results = self.storage.search_graph(space, entity, limit=10)
        return {
            "entity": entity,
            "related_memories": results,
            "count": len(results),
        }

    async def status(self) -> dict:
        """Return service health and storage statistics."""
        stats = self.storage.get_stats(self.space)
        graph_stats = self.storage.get_graph_stats(self.space)
        total = stats.get("total_count", 0) or 0
        embeddings = self.storage.count_embeddings(self.space)
        fts_entries = self.storage.count_fts_entries(self.space)
        embedding_coverage = round((embeddings / total) * 100, 2) if total else 100.0
        fts_coverage = round((fts_entries / total) * 100, 2) if total else 100.0
        try:
            import jieba  # noqa: F401
            jieba_available = True
        except ImportError:
            jieba_available = False
        return {
            "space": self.space,
            "embedding_available": self.embedder.available,
            "embedding_provider": self.embedder.provider,
            "embed_model": self.config.embed_model,
            "embed_dim": self.embedder.dim,
            "embedding_queue_pending": self.embedder.queue_size,
            "embedding_processed_count": self.embedder.processed_count,
            "embedding_failed_count": self.embedder.failed_count,
            "embeddings_stored_count": embeddings,
            "embedding_coverage_percent": embedding_coverage,
            "fts_entries_count": fts_entries,
            "fts_coverage_percent": fts_coverage,
            "fts_index_health": "ok" if fts_entries == total else "needs_reindex",
            "reranker_available": self.reranker.available,
            "rerank_model": self.config.rerank_model,
            "rerank_candidates": self.config.rerank_candidates,
            "llm_available": self.llm.available,
            "llm_model": self.config.llm_model,
            "jieba_available": jieba_available,
            "jieba_enabled": self.config.jieba_enabled,
            "cosine_dedup_threshold": self.config.cosine_dedup_threshold,
            "briefing_recent": self.config.briefing_recent,
            "briefing_important": self.config.briefing_important,
            "api_timeout_seconds": self.config.api_timeout_seconds,
            "embedding_api_metrics": self.embedder.metrics_snapshot(),
            "rerank_api_metrics": self.reranker.metrics_snapshot(),
            "llm_api_metrics": self.llm.metrics_snapshot(),
            "rerank_last_applied": self.reranker.last_applied,
            "rerank_last_fallback_reason": self.reranker.last_fallback_reason,
            "rerank_last_latency_ms": self.reranker.last_latency_ms,
            "last_recall_latency_ms": self._last_recall_latency_ms,
            "recall_latency_metrics": self._recall_latency_snapshot(),
            "last_recall_trace": self._last_recall_trace,
            "spaces": self.storage.list_spaces(),
            **graph_stats,
            **stats,
        }

    async def export(self, layer: str = None, format: str = "markdown") -> dict:
        """Export memories as JSON or Markdown."""
        space = self.space
        memories = self.storage.export_memories(space, layer=layer)
        if format == "json":
            return {"memories": [m.to_dict() for m in memories], "count": len(memories), "space": space, "format": "json"}
        # Markdown
        from datetime import datetime, timezone
        lines = [f"# EverMind Export — {space}", "", f"*{len(memories)} memories*", ""]
        layers_map = {}
        for m in memories:
            layers_map.setdefault(m.layer, []).append(m)
        for lyr, label in [("archive", "## Archive"), ("semantic", "## Semantic"), ("procedural", "## Procedural"), ("episodic", "## Episodic"), ("working", "## Working")]:
            if lyr in layers_map:
                lines += [label, ""]
                for m in layers_map[lyr]:
                    dt = datetime.fromtimestamp(m.created_at / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    tags_str = f" `{'` `'.join(m.tags)}`" if m.tags else ""
                    lines += [f"- **[{m.memory_type}]**{tags_str} *{dt}*", f"  {m.content}", ""]
        return {"content": "\n".join(lines), "count": len(memories), "space": space, "format": "markdown"}

    async def compact(self, older_than_days: int = 30) -> dict:
        """Compact old episodic memories into a summary."""
        result = self.storage.compact_episodic(self.space, older_than_days=older_than_days)
        if result["summarized"] > 0:
            self.storage.log_event(self.space, "compact", result["created_id"], {"summarized_count": result["summarized"]})
            self._signal_briefing_refresh()
        return result

    async def list_tags(self) -> dict:
        """Return all tags used in this space."""
        tags = self.storage.list_tags(self.space)
        return {"tags": tags, "count": len(tags), "space": self.space}

    async def list_spaces(self) -> dict:
        """Return all project spaces known to the local store."""
        spaces = self.storage.list_spaces()
        return {"spaces": spaces, "count": len(spaces), "current": self.space}

    async def reindex(self, all_spaces: bool = False) -> dict:
        """Rebuild FTS and graph indexes with current token/entity extraction."""
        target_space = None if all_spaces else self.space
        result = self.storage.reindex_fts(target_space)
        if self.config.graph_enabled:
            result.update(self.storage.reindex_graph(target_space))
        self.storage.log_event(
            self.space,
            "reindex",
            None,
            {
                "all_spaces": all_spaces,
                "reindexed": result["reindexed"],
                "graph_reindexed": result.get("graph_reindexed", 0),
            },
        )
        self._signal_briefing_refresh()
        return result

    async def health(self) -> dict:
        """Return memory health and observability metrics."""
        stats = self.storage.get_stats(self.space)
        graph_stats = self.storage.get_graph_stats(self.space)
        total = stats.get("total_count", 0) or 0
        embeddings = self.storage.count_embeddings(self.space)
        fts_entries = self.storage.count_fts_entries(self.space)
        duplicates = self.storage.count_exact_duplicates(self.space)
        expired = self.storage.count_expired_working(self.space)
        embedding_coverage = round((embeddings / total) * 100, 2) if total else 100.0
        fts_coverage = round((fts_entries / total) * 100, 2) if total else 100.0
        duplicate_rate = round((duplicates / total) * 100, 2) if total else 0.0
        return {
            "space": self.space,
            "total_count": total,
            "embedding_coverage_percent": embedding_coverage,
            "fts_coverage_percent": fts_coverage,
            "fts_index_health": "ok" if fts_entries == total else "needs_reindex",
            "reranker_available": self.reranker.available,
            "llm_available": self.llm.available,
            "embedding_queue_pending": self.embedder.queue_size,
            "embedding_failed_count": self.embedder.failed_count,
            "embedding_processed_count": self.embedder.processed_count,
            "expired_working_count": expired,
            "exact_duplicate_groups": duplicates,
            "duplicate_rate_percent": duplicate_rate,
            "api_timeout_seconds": self.config.api_timeout_seconds,
            "embedding_api_metrics": self.embedder.metrics_snapshot(),
            "rerank_api_metrics": self.reranker.metrics_snapshot(),
            "llm_api_metrics": self.llm.metrics_snapshot(),
            "rerank_last_applied": self.reranker.last_applied,
            "rerank_last_fallback_reason": self.reranker.last_fallback_reason,
            "rerank_last_latency_ms": self.reranker.last_latency_ms,
            "last_recall_latency_ms": self._last_recall_latency_ms,
            "recall_latency_metrics": self._recall_latency_snapshot(),
            "last_recall_trace": self._last_recall_trace,
            **graph_stats,
            "spaces": self.storage.list_spaces(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _briefing_worker_loop(self) -> None:
        """Single background thread that refreshes briefing cache on demand."""
        while True:
            triggered = self._briefing_event.wait(timeout=120)
            self._briefing_event.clear()
            if triggered:
                self._refresh_briefing_bg()

    def _signal_briefing_refresh(self) -> None:
        """Signal the briefing worker to refresh (non-blocking)."""
        self._briefing_event.set()

    def _on_embedding_ready(self, memory_id: str, vec: list[float]) -> None:
        """
        Callback invoked by EmbeddingManager when a background embedding
        finishes. Writes the vector to storage and refreshes the briefing cache.
        """
        rowid = self.storage.get_memory_rowid(memory_id)
        if rowid:
            self.storage.update_embedding(rowid, vec)
            logger.debug("Embedding stored for memory_id=%s rowid=%s", memory_id, rowid)
        else:
            logger.debug("Memory %s deleted before embedding callback finished", memory_id)

        self.storage.refresh_briefing_cache(
            self.space,
            recent_limit=self.config.briefing_recent,
            important_limit=self.config.briefing_important,
        )

    def _refresh_briefing_bg(self) -> None:
        """Background thread target: refresh the briefing cache silently."""
        try:
            self.storage.refresh_briefing_cache(
                self.space,
                recent_limit=self.config.briefing_recent,
                important_limit=self.config.briefing_important,
            )
        except Exception as e:
            logger.debug("Briefing refresh error: %s", e)

    def _record_recall_trace(
        self,
        space: str,
        query: str,
        requested_mode: str,
        mode_used: str,
        fts_candidates: int,
        vec_candidates: int,
        returned: int,
        rerank_applied: bool,
        rerank_fallback_reason: str | None,
        latency_ms: float,
        *,
        all_spaces: bool = False,
    ) -> None:
        self._last_recall_latency_ms = latency_ms
        self._recall_latencies.append(latency_ms)
        trace = {
            "query": query[:100],
            "requested_mode": requested_mode,
            "mode_used": mode_used,
            "fts_candidates": fts_candidates,
            "vec_candidates": vec_candidates,
            "returned": returned,
            "rerank_applied": rerank_applied,
            "rerank_fallback_reason": rerank_fallback_reason,
            "rerank_scores": self.reranker.last_scores[:10],
            "latency_ms": latency_ms,
            "all_spaces": all_spaces,
        }
        self._last_recall_trace = trace
        self.storage.log_event(space, "recall_result", None, trace)

    def _recall_latency_snapshot(self) -> dict:
        latencies = list(self._recall_latencies)
        return {
            "recent_count": len(latencies),
            "latency_p50_ms": self._percentile(latencies, 0.50),
            "latency_p95_ms": self._percentile(latencies, 0.95),
        }

    @staticmethod
    def _percentile(values: list[float], quantile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = round((len(ordered) - 1) * quantile)
        return round(ordered[index], 3)

    def _rerank_if_available(
        self,
        query: str,
        candidates: list,
        limit: int,
    ) -> tuple[list, bool, str | None]:
        if not candidates:
            return [], False, "no_candidates"
        if not self.reranker.available:
            return candidates[:limit], False, "unavailable"
        reranked = self.reranker.rerank(query, candidates, top_k=limit)
        if getattr(self.reranker, "last_applied", True):
            return reranked, True, None
        return reranked[:limit], False, getattr(
            self.reranker,
            "last_fallback_reason",
            "unknown",
        )
