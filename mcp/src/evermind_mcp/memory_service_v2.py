"""
EverMind Memory Service v2

Replaces the old 2876-line memory_service.py with a clean, modular implementation
that delegates storage, embedding, and type concerns to dedicated modules.
"""

import logging
import threading
import time
from typing import Optional

from .storage import EmbeddedStorage
from .embedding import EmbeddingManager
from .config_v2 import EverMindConfig

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

    if any(k in lower for k in ("how to", "步骤", "流程", "procedure", "deploy", "run")):
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
        )
        self.embedder.set_callback(self._on_embedding_ready)
        self.space = config.default_space

        # CHANGE 6: Check embedding dimension matches storage expectation
        if self.embedder.available:
            actual_dim = self.embedder.dim
            if not self.storage.check_embed_dim(actual_dim):
                logger.warning("Vector search disabled due to embedding dimension mismatch.")
                self.embedder._enabled = False

        # Single persistent briefing worker (replaces per-call thread spawning)
        self._briefing_event = threading.Event()
        self._briefing_worker = threading.Thread(
            target=self._briefing_worker_loop,
            daemon=True,
            name="evermind-briefing",
        )
        self._briefing_worker.start()

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

        # fuzzy dedup removed - too noisy, exact match only now

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
    ) -> dict:
        """
        Retrieve memories matching a query using FTS, semantic search,
        or hybrid RRF fusion.
        """
        if space is None:
            space = self.space

        # Quick working-memory expiry
        self.storage.expire_working_memories(space)

        # Log the recall event
        self.storage.log_event(space, "recall", None, {"query": query[:100]})

        fts_results: list = []
        vec_results: list = []

        # Full-text search
        if mode in ("hybrid", "fts"):
            fts_results = self.storage.search_fts(query, space, limit=limit * 2, layer=layer, tags=tags)

        # Semantic / vector search
        if mode in ("hybrid", "semantic"):
            vec = self.embedder.encode(query)
            if vec is not None:
                vec_results = self.storage.search_vec(vec, space, limit=limit * 2)
                if layer:
                    vec_results = [r for r in vec_results if r.layer == layer]

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
                scored.append((score, mid))

            scored.sort(key=lambda x: x[0], reverse=True)
            final_list = [id_to_memory[mid] for _, mid in scored[:limit]]
            mode_used = "hybrid"

        elif fts_results:
            final_list = fts_results[:limit]
            mode_used = "fts"

        elif vec_results:
            final_list = vec_results[:limit]
            mode_used = "semantic"

        else:
            return {
                "results": [],
                "mode": mode,
                "count": 0,
                "query": query,
            }

        return {
            "results": [m.to_dict() for m in final_list],
            "mode": mode_used,
            "count": len(final_list),
            "query": query,
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

        return cache.to_dict()

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
        return {
            "space": self.space,
            "embedding_available": self.embedder.available,
            "embed_model": self.config.embed_model,
            **stats,
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
            logger.warning("No rowid found for memory_id=%s; embedding discarded", memory_id)

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
