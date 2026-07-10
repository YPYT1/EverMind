"""
EverMind Memory Service v2

Replaces the old 2876-line memory_service.py with a clean, modular implementation
that delegates storage, embedding, and type concerns to dedicated modules.
"""

import hashlib
import json
import logging
import re
import threading
import time
from collections import deque

from .storage import EmbeddedStorage
from .embedding import EmbeddingManager
from .reranker import RerankerManager
from .llm import LLMManager
from .legacy_migration import LegacyCatalogMigrator
from .config_v2 import EverMindConfig
from .content_guard import scan_sensitive_content
from .archive_engine import ArchiveEngine, archive_project_path
from .codebase_engine import CodebaseEngine
from .provider_boundary import local_provider_boundary
from .project_catalog import UnifiedProjectResolver

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

VERIFIED_TAGS = {"codebase-verified", "verified"}
NEGATION_PATTERNS = (
    "不存在",
    "没有",
    "无 ",
    "无此",
    "not exist",
    "does not exist",
    "no ",
    "missing",
)
AFFIRMATION_PATTERNS = (
    "存在",
    "在 ",
    "位于",
    "管理",
    "manages",
    "uses",
    "use ",
    "exposes",
    "contains",
    "存在于",
)
ENTITY_PATTERN = re.compile(
    r"[\w./\\-]+\.(?:py|ts|tsx|js|jsx|cts|mts|vue|go|rs|java|cs|cpp|c|h|md|json|toml|yaml|yml)|"
    r"\b[A-Z][A-Za-z0-9_]{2,}\b"
)


def _detect_memory_type(content: str, importance: int) -> str:
    """Auto-detect memory type from content keywords."""
    lower = content.lower()

    if any(k in lower for k in ("bug", "error", "fix", "crash", "exception")):
        return TYPE_BUG

    if any(
        k in lower
        for k in (
            "how to",
            "步骤",
            "流程",
            "procedure",
            "deploy",
            "run",
            "如何",
            "方法",
            "命令",
            "运行",
            "执行",
        )
    ):
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
        config.home.mkdir(parents=True, exist_ok=True)
        self.storage = EmbeddedStorage(config.db_path(config.default_space))
        LegacyCatalogMigrator(config.home, self.storage).migrate()
        self.storage.ensure_project(config.default_space)
        self.projects = UnifiedProjectResolver(self.storage)
        resolved_workspace = None
        if config.workspace_root is not None:
            try:
                resolved_workspace = self.projects.resolve_workspace(
                    config.workspace_root
                )
            except (OSError, ValueError):
                logger.debug("Could not resolve configured workspace", exc_info=True)
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
        self.space = (
            resolved_workspace["project_id"]
            if resolved_workspace is not None
            else config.default_space
        )
        self.workspace_id = (
            resolved_workspace["workspace_id"]
            if resolved_workspace is not None
            else None
        )
        self.codebase = CodebaseEngine(config)
        self.archive = ArchiveEngine(config)
        self._last_recall_latency_ms: float | None = None
        self._recall_latencies: deque[float] = deque(maxlen=200)
        self._last_recall_trace: dict = {}

        # CHANGE 6: Check embedding dimension matches storage expectation
        if self.embedder.available:
            actual_dim = self.embedder.dim
            if not self.storage.check_embed_dim(actual_dim):
                logger.warning(
                    "Vector search disabled due to embedding dimension mismatch."
                )
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
        self._closing = threading.Event()
        self._briefing_event = threading.Event()
        self._briefing_worker = threading.Thread(
            target=self._briefing_worker_loop,
            daemon=True,
            name="evermind-briefing",
        )
        self._briefing_worker.start()

    def set_space(self, space: str) -> None:
        """Switch the active project while retaining the shared catalog."""
        if not space or space == self.space:
            return
        self.storage.ensure_project(space)
        self.space = space

    def close(self) -> None:
        """Stop workers before closing the active SQLite connections."""
        if not self._closing.is_set():
            self._closing.set()
            self._briefing_event.set()
        self.embedder.close()
        self._briefing_worker.join(timeout=5.0)
        self.storage.close_all()

    async def delete_project(
        self,
        *,
        project: str | None = None,
        project_name: str | None = None,
    ) -> dict:
        """Detach one unified project while preserving all durable user data."""
        if not project and not project_name:
            return {
                "ok": False,
                "code": "PROJECT_IDENTIFIER_REQUIRED",
                "message": "project or project_name is required",
            }
        try:
            resolved_project = (
                self.projects.resolve_project(project) if project else None
            )
            resolved_name = (
                self.projects.resolve_project(project_name) if project_name else None
            )
        except ValueError as exc:
            return {
                "ok": False,
                "code": "PROJECT_NOT_FOUND",
                "message": str(exc),
            }
        if (
            resolved_project
            and resolved_name
            and resolved_project["project_id"] != resolved_name["project_id"]
        ):
            return {
                "ok": False,
                "code": "PROJECT_IDENTIFIER_MISMATCH",
                "message": "project and project_name resolve to different projects",
            }

        target = resolved_project or resolved_name
        if target is None:
            return {
                "ok": False,
                "code": "PROJECT_NOT_FOUND",
                "message": "project could not be resolved",
            }
        project_id = target["project_id"]
        operation_id = "delete-" + hashlib.sha256(project_id.encode()).hexdigest()[:24]
        now = int(time.time() * 1000)
        existing_operation = self.storage.conn.execute(
            "SELECT * FROM project_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if (
            existing_operation is not None
            and existing_operation["state"] == "completed"
        ):
            return {
                "ok": True,
                "status": "detached",
                "project_id": project_id,
                "resumed": False,
                "already_completed": True,
            }
        completed_steps = (
            set(json.loads(existing_operation["completed_steps"]))
            if existing_operation is not None
            else set()
        )
        self.storage.conn.execute(
            """
            INSERT INTO project_operations
                (operation_id, kind, state, payload, completed_steps, error,
                 created_at, updated_at)
            VALUES (?, 'delete_project', 'running', ?, ?, NULL, ?, ?)
            ON CONFLICT(operation_id) DO UPDATE SET
                state='running', error=NULL, updated_at=excluded.updated_at
            """,
            (
                operation_id,
                json.dumps({"project_id": project_id}),
                json.dumps(sorted(completed_steps)),
                now,
                now,
            ),
        )
        self.storage.conn.commit()

        workspaces = self.storage.conn.execute(
            "SELECT workspace_id FROM workspaces WHERE project_id=? ORDER BY workspace_id",
            (project_id,),
        ).fetchall()
        for workspace in workspaces:
            workspace_id = workspace["workspace_id"]
            step = f"codebase:{workspace_id}"
            if step in completed_steps:
                continue
            result = self.codebase.call("delete_project", {"project": workspace_id})
            if result.get("ok") is False:
                self.storage.conn.execute(
                    """
                    UPDATE project_operations
                    SET error=?, completed_steps=?, updated_at=?
                    WHERE operation_id=?
                    """,
                    (
                        json.dumps(result),
                        json.dumps(sorted(completed_steps)),
                        int(time.time() * 1000),
                        operation_id,
                    ),
                )
                self.storage.conn.commit()
                return {
                    "ok": False,
                    "code": "PROJECT_DETACH_CODEBASE_FAILED",
                    "project_id": project_id,
                    "operation_id": operation_id,
                    "cause": result,
                    "retryable": True,
                }
            completed_steps.add(step)
            self._record_project_operation_steps(operation_id, completed_steps)

        if "basic_binding" not in completed_steps:
            self.storage.conn.execute(
                "DELETE FROM basic_project_bindings WHERE project_id=?", (project_id,)
            )
            completed_steps.add("basic_binding")
            self._record_project_operation_steps(operation_id, completed_steps)

        detached_at = int(time.time() * 1000)
        self.storage.conn.execute(
            """
            UPDATE workspaces
            SET state='detached', detached_at=?, updated_at=?
            WHERE project_id=?
            """,
            (detached_at, detached_at, project_id),
        )
        self.storage.conn.execute(
            """
            UPDATE projects
            SET state='detached', detached_at=?, updated_at=?
            WHERE project_id=?
            """,
            (detached_at, detached_at, project_id),
        )
        completed_steps.add("catalog_detached")
        self.storage.conn.execute(
            """
            UPDATE project_operations
            SET state='completed', completed_steps=?, error=NULL, updated_at=?
            WHERE operation_id=?
            """,
            (
                json.dumps(sorted(completed_steps)),
                detached_at,
                operation_id,
            ),
        )
        self.storage.conn.commit()
        return {
            "ok": True,
            "status": "detached",
            "project_id": project_id,
            "workspace_ids": [workspace["workspace_id"] for workspace in workspaces],
            "operation_id": operation_id,
            "preserved": ["repository", "markdown_archive", "durable_memories"],
        }

    def _record_project_operation_steps(
        self, operation_id: str, completed_steps: set[str]
    ) -> None:
        self.storage.conn.execute(
            """
            UPDATE project_operations
            SET completed_steps=?, updated_at=?
            WHERE operation_id=?
            """,
            (
                json.dumps(sorted(completed_steps)),
                int(time.time() * 1000),
                operation_id,
            ),
        )
        self.storage.conn.commit()

    def call_codebase(self, tool: str, arguments: dict | None = None) -> dict:
        args = dict(arguments or {})
        if tool == "index_repository" and args.get("repo_path"):
            resolved = self.projects.resolve_workspace(args["repo_path"])
            args["project"] = resolved["workspace_id"]
            args["name"] = resolved["workspace_id"]
            args["_evermind_workspace_id"] = resolved["workspace_id"]
            args["_evermind_project_id"] = resolved["project_id"]
            args["_evermind_display_name"] = resolved["display_name"]
            result = self.codebase.call(tool, args)
            if result.get("ok") is not False:
                self.set_space(resolved["project_id"])
                self.workspace_id = resolved["workspace_id"]
                result.update(
                    project=resolved["workspace_id"],
                    workspace_id=resolved["workspace_id"],
                    project_id=resolved["project_id"],
                    display_name=resolved["display_name"],
                )
            return result

        if tool != "list_projects" and args.get("project"):
            try:
                args["project"] = self.projects.resolve_codebase_workspace(
                    str(args["project"])
                )
            except ValueError:
                # Preserve compatibility with pre-catalog engine identifiers.
                pass
        return self.codebase.call(tool, args)

    def call_archive(self, tool: str, arguments: dict | None = None) -> dict:
        args = dict(arguments or {})
        project_scoped = tool in {
            "write_note",
            "read_note",
            "delete_note",
            "edit_note",
            "build_context",
            "search_notes",
            "schema_validate",
            "schema_infer",
            "schema_diff",
        }
        resolved_project = None
        identifier = args.get("project_id") or args.get("project")
        if identifier:
            try:
                resolved_project = self.projects.resolve_project(str(identifier))
                project_id = resolved_project["project_id"]
            except ValueError:
                project_id = str(identifier)
            args["project"] = project_id
            args["project_id"] = project_id
        elif project_scoped:
            args["project"] = self.space
            args["project_id"] = self.space
            try:
                resolved_project = self.projects.resolve_project(self.space)
            except ValueError:
                resolved_project = None
        if project_scoped and resolved_project is not None:
            project_id = resolved_project["project_id"]
            self.projects.bind_basic_project(
                project_id,
                external_id=project_id,
                name=resolved_project["display_name"],
                path=archive_project_path(self.config, project_id),
            )
        return self.archive.call(tool, args)

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
        meta: dict | None = None,
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
            self.storage.attach_memory_source(
                exact.id,
                space,
                importance=importance,
                tags=tags,
                meta=meta,
            )
            self.storage.log_event(
                space, "remember_merged", exact.id, {"reason": "exact_match"}
            )
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
                                entities = self.storage.extract_entities_from_content(
                                    content
                                )
                                if entities:
                                    self.storage.link_memory_to_entities(
                                        candidate.id,
                                        space,
                                        entities,
                                    )
                            self.storage.log_event(
                                space,
                                "remember_merged",
                                candidate.id,
                                {"reason": "cosine_similarity", "score": round(sim, 4)},
                            )
                            return {
                                "id": candidate.id,
                                "action": "merged",
                                "layer": candidate.layer,
                                "type": candidate.memory_type,
                                "similar_merged": True,
                                "similarity": round(sim, 4),
                            }

        # Insert new memory
        meta = dict(meta or {})
        conflicts = self._detect_conflicts(content, tags or [], meta)
        memory, inserted = self.storage.insert_memory_atomic(
            content=content,
            space=space,
            layer=layer,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            role=role,
            meta=meta,
        )

        if not inserted:
            self.storage.log_event(
                space,
                "remember_merged",
                memory.id,
                {"reason": "exact_match_race"},
            )
            return {
                "id": memory.id,
                "action": "merged",
                "layer": memory.layer,
                "type": memory.memory_type,
                "similar_merged": True,
            }

        # Enqueue background embedding
        self.embedder.enqueue(memory.id, content)

        # Log the event
        self.storage.log_event(space, "remember", memory.id, {"importance": importance})

        # CHANGE 4: Graph integration - link entities after insert
        if self.config.graph_enabled:
            entities = self.storage.extract_entities_from_content(content)
            if entities:
                self.storage.link_memory_to_entities(memory.id, space, entities)
                logger.debug(
                    "Graph: linked %d entities to memory %s", len(entities), memory.id
                )

        # Trigger briefing refresh in background if important enough
        if importance >= 1:
            self._signal_briefing_refresh()

        logger.debug(
            "Memory stored id=%s layer=%s type=%s", memory.id, layer, memory_type
        )
        return {
            "id": memory.id,
            "action": "stored",
            "layer": layer,
            "type": memory_type,
            "similar_merged": False,
            "conflicts": conflicts,
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
        min_score: float | None = None,
    ) -> dict:
        """
        Retrieve memories matching a query using FTS, semantic search,
        hybrid RRF fusion, and optional cross-encoder reranking.
        """
        started = time.perf_counter()
        if space is None:
            space = self.space
        effective_min_score = (
            self.config.recall_min_score if min_score is None else min_score
        )

        candidate_limit = max(
            limit * 2,
            self.config.rerank_candidates if self.reranker.available else limit * 2,
        )

        # Quick working-memory expiry
        self.storage.expire_working_memories(space)

        # Log the recall event
        self.storage.log_event(space, "recall", None, {"query": query[:100]})

        fts_results: list = []
        vec_results: list = []

        # Full-text search
        if mode in ("hybrid", "fts"):
            fts_results = self.storage.search_fts_global(
                query,
                space,
                limit=candidate_limit,
                layer=layer,
                tags=tags,
            )
            if not fts_results:
                fts_results = self._search_entity_fallbacks(
                    query,
                    space,
                    candidate_limit,
                    layer=layer,
                    tags=tags,
                )

        # Semantic / vector search
        if mode in ("hybrid", "semantic"):
            vec = self.embedder.encode(query)
            if vec is not None:
                vec_results = self.storage.search_vec_global(
                    vec,
                    space,
                    limit=candidate_limit,
                )
                if layer:
                    vec_results = [r for r in vec_results if r.layer == layer]
                if tags:
                    wanted = set(tags)
                    vec_results = [
                        r for r in vec_results if wanted.intersection(set(r.tags))
                    ]

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
                all_spaces=all_spaces,
                min_score=effective_min_score if min_score is not None else None,
            )
            return {
                "results": [],
                "mode": mode,
                "count": 0,
                "query": query,
                "all_spaces": all_spaces,
                "latency_ms": latency_ms,
                "rerank_applied": False,
                "rerank_fallback_reason": "no_candidates",
                "min_score": effective_min_score if min_score is not None else None,
                "threshold_reason": None,
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
        threshold_min_score = (
            effective_min_score if min_score is not None or rerank_applied else None
        )
        final_list, threshold_reason = self._filter_by_min_score(
            final_list,
            threshold_min_score,
        )

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
            all_spaces=all_spaces,
            min_score=threshold_min_score,
            threshold_reason=threshold_reason,
        )
        results, conflicts = self._prepare_results(final_list, query=query)
        return {
            "results": results,
            "mode": mode_used,
            "count": len(final_list),
            "query": query,
            "all_spaces": all_spaces,
            "latency_ms": latency_ms,
            "rerank_applied": rerank_applied,
            "rerank_fallback_reason": rerank_fallback,
            "min_score": threshold_min_score,
            "threshold_reason": threshold_reason,
            "fts_candidates": len(fts_results),
            "vec_candidates": len(vec_results),
            "conflicts": conflicts,
            "forget_suggestions": self._forget_suggestions(conflicts),
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
        memories = self.storage.list_memories_global(
            space,
            layer=layer,
            tags=tags,
            limit=limit,
        )
        results = []
        for memory in memories:
            item = memory.to_dict()
            item["source_projects"] = self.storage.source_projects(memory.id)
            results.append(item)
        return {
            "memories": results,
            "count": len(memories),
            "filter": {"layer": layer, "tags": tags},
        }

    async def update_memory(
        self,
        memory_id: str,
        content: str | None = None,
        importance: int | None = None,
        tags: list | None = None,
        memory_type: str | None = None,
        meta: dict | None = None,
    ) -> dict:
        """Update a memory by ID and rebuild derived indexes as needed."""
        existing = self.storage.get_memory(memory_id)
        if existing is None:
            return {"updated": False, "id": memory_id, "error": "not found"}

        if (
            content is None
            and importance is None
            and tags is None
            and memory_type is None
            and meta is None
        ):
            return {"updated": False, "id": memory_id, "error": "no fields to update"}

        new_content = existing.content if content is None else content
        content_changed = new_content != existing.content
        new_importance = existing.importance if importance is None else importance
        requested_type = (
            "auto"
            if memory_type is None and content_changed
            else (existing.memory_type if memory_type is None else memory_type)
        )
        new_type = (
            _detect_memory_type(new_content, new_importance)
            if requested_type == "auto"
            else requested_type
        )
        new_layer = _assign_layer(new_importance, new_type)
        new_tags = existing.tags if tags is None else tags
        new_meta = existing.meta if meta is None else dict(meta)

        if content_changed and self.config.sensitive_memory_block:
            sensitive_matches = scan_sensitive_content(new_content)
            if sensitive_matches:
                self.storage.log_event(
                    existing.space,
                    "update_memory_rejected",
                    memory_id,
                    {
                        "reason": "sensitive_content",
                        "categories": sorted({m.category for m in sensitive_matches}),
                    },
                )
                return {
                    "updated": False,
                    "id": memory_id,
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

        updated = self.storage.update_memory(
            memory_id,
            content=new_content,
            layer=new_layer,
            memory_type=new_type,
            importance=new_importance,
            tags=new_tags,
            meta=new_meta,
        )
        if updated is None:
            return {"updated": False, "id": memory_id, "error": "not found"}

        if content_changed:
            self.embedder.enqueue(updated.id, updated.content)
            if self.config.graph_enabled:
                entities = self.storage.extract_entities_from_content(updated.content)
                if entities:
                    self.storage.link_memory_to_entities(
                        updated.id, updated.space, entities
                    )

        conflicts = self._detect_conflicts(updated.content, updated.tags, updated.meta)
        self.storage.log_event(
            updated.space,
            "memory_updated",
            updated.id,
            {
                "content_changed": content_changed,
                "importance": updated.importance,
                "layer": updated.layer,
                "type": updated.memory_type,
            },
        )
        self._signal_briefing_refresh()
        return {
            "updated": True,
            "id": updated.id,
            "action": "updated",
            "layer": updated.layer,
            "type": updated.memory_type,
            "importance": updated.importance,
            "tags": updated.tags,
            "meta": updated.meta,
            "content_changed": content_changed,
            "conflicts": conflicts,
            "forget_suggestions": self._forget_suggestions(conflicts),
        }

    async def forget(self, memory_id: str) -> dict:
        """Permanently delete a memory by ID."""
        deleted = self.storage.delete_memory(memory_id)
        if deleted:
            self.storage.log_event(self.space, "forget", memory_id, {})
            self._signal_briefing_refresh()
            return {"deleted": True, "id": memory_id}
        return {"deleted": False, "id": memory_id, "error": "not found"}

    async def briefing(self, fast: bool = False) -> dict:
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
        if self.config.llm_briefing_summary and not fast:
            summary = self.llm.summarize_briefing(memories_for_summary)
            if summary:
                data["context_summary"] = summary
        data["fast"] = fast
        data["warnings"] = [
            m
            for m in memories_for_summary
            if (m.get("memory_type") or m.get("type")) == TYPE_BUG
        ][:5]
        data["decisions"] = [
            m
            for m in memories_for_summary
            if m.get("layer") == LAYER_ARCHIVE
            or (m.get("memory_type") or m.get("type")) == TYPE_DECISION
        ][:5]
        return data

    async def graph_explore(self, entity: str) -> dict:
        """Explore graph relationships for a given entity."""
        space = self.space
        results = self.storage.search_graph(space, entity, limit=10)
        memories = []
        for item in results:
            memory = item.get("memory") if isinstance(item, dict) else None
            if isinstance(memory, dict):
                memories.append(memory)
        conflicts = self._detect_conflicts_in_dicts(memories, query=entity)
        return {
            "entity": entity,
            "related_memories": results,
            "count": len(results),
            "conflicts": conflicts,
            "forget_suggestions": self._forget_suggestions(conflicts),
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
        codebase_meta = self.codebase.metadata()
        archive_meta = self.archive.metadata()
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
            "codebase_engine_available": True,
            "codebase_engine": "evermind-code-graph",
            "codebase_engine_path": codebase_meta["binary_path"],
            "codebase_backend": codebase_meta["active_backend"],
            "codebase_source_integrated": codebase_meta["source_integrated"],
            "codebase_binary_available": codebase_meta["binary_available"],
            "codebase_source_path": codebase_meta["source_path"],
            "archive_engine_available": True,
            "archive_engine": "evermind-archive",
            "archive_backend": archive_meta["backend"],
            "archive_source_integrated": archive_meta["source_integrated"],
            "archive_source_path": archive_meta["source_path"],
            "archive_license": archive_meta["license"],
            "archive_engine_path": None,
            "archive_root": str(self.config.archive_root),
            "provider_boundary": local_provider_boundary(),
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
            return {
                "memories": [m.to_dict() for m in memories],
                "count": len(memories),
                "space": space,
                "format": "json",
            }
        # Markdown
        from datetime import datetime, timezone

        lines = [f"# EverMind Export — {space}", "", f"*{len(memories)} memories*", ""]
        layers_map = {}
        for m in memories:
            layers_map.setdefault(m.layer, []).append(m)
        for lyr, label in [
            ("archive", "## Archive"),
            ("semantic", "## Semantic"),
            ("procedural", "## Procedural"),
            ("episodic", "## Episodic"),
            ("working", "## Working"),
        ]:
            if lyr in layers_map:
                lines += [label, ""]
                for m in layers_map[lyr]:
                    dt = datetime.fromtimestamp(
                        m.created_at / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                    tags_str = f" `{'` `'.join(m.tags)}`" if m.tags else ""
                    lines += [
                        f"- **[{m.memory_type}]**{tags_str} *{dt}*",
                        f"  {m.content}",
                        "",
                    ]
        return {
            "content": "\n".join(lines),
            "count": len(memories),
            "space": space,
            "format": "markdown",
        }

    async def compact(self, older_than_days: int = 30) -> dict:
        """Compact old episodic memories into a summary."""
        result = self.storage.compact_episodic(
            self.space, older_than_days=older_than_days
        )
        if result["summarized"] > 0:
            self.storage.log_event(
                self.space,
                "compact",
                result["created_id"],
                {"summarized_count": result["summarized"]},
            )
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
        codebase_meta = self.codebase.metadata()
        archive_meta = self.archive.metadata()
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
            "codebase_engine_available": True,
            "codebase_engine": "evermind-code-graph",
            "codebase_engine_path": codebase_meta["binary_path"],
            "codebase_backend": codebase_meta["active_backend"],
            "codebase_source_integrated": codebase_meta["source_integrated"],
            "codebase_binary_available": codebase_meta["binary_available"],
            "codebase_source_path": codebase_meta["source_path"],
            "archive_engine_available": True,
            "archive_engine": "evermind-archive",
            "archive_backend": archive_meta["backend"],
            "archive_source_integrated": archive_meta["source_integrated"],
            "archive_source_path": archive_meta["source_path"],
            "archive_license": archive_meta["license"],
            "archive_root": str(self.config.archive_root),
            "provider_boundary": local_provider_boundary(),
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
        while not self._closing.is_set():
            triggered = self._briefing_event.wait(timeout=120)
            self._briefing_event.clear()
            if triggered and not self._closing.is_set():
                self._refresh_briefing_bg()

    def _signal_briefing_refresh(self) -> None:
        """Signal the briefing worker to refresh (non-blocking)."""
        if not self._closing.is_set():
            self._briefing_event.set()

    def _on_embedding_ready(self, memory_id: str, vec: list[float]) -> None:
        """
        Callback invoked by EmbeddingManager when a background embedding
        finishes. Writes the vector to storage and refreshes the briefing cache.
        """
        if self._closing.is_set():
            return
        rowid = self.storage.get_memory_rowid(memory_id)
        if rowid:
            self.storage.update_embedding(rowid, vec)
            logger.debug("Embedding stored for memory_id=%s rowid=%s", memory_id, rowid)
        else:
            logger.debug(
                "Memory %s deleted before embedding callback finished", memory_id
            )

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
        min_score: float | None = None,
        threshold_reason: str | None = None,
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
            "min_score": min_score,
            "threshold_reason": threshold_reason,
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
            return (
                self._prioritize_verified_conflicts(candidates, query)[:limit],
                False,
                "unavailable",
            )
        top_k = min(len(candidates), max(limit, limit + 5))
        reranked = self.reranker.rerank(query, candidates, top_k=top_k)
        reranked = self._prioritize_verified_conflicts(reranked, query)
        if getattr(self.reranker, "last_applied", True):
            return reranked[:limit], True, None
        return (
            reranked[:limit],
            False,
            getattr(
                self.reranker,
                "last_fallback_reason",
                "unknown",
            ),
        )

    @staticmethod
    def _filter_by_min_score(
        memories: list, min_score: float | None
    ) -> tuple[list, str | None]:
        if min_score is None or min_score <= 0:
            return memories, None
        filtered = [memory for memory in memories if memory.score >= min_score]
        if memories and not filtered:
            return [], "below_threshold"
        if len(filtered) < len(memories):
            return filtered, "partial_below_threshold"
        return filtered, None

    def _search_entity_fallbacks(
        self,
        query: str,
        space: str,
        limit: int,
        *,
        layer: str | None = None,
        tags: list | None = None,
    ) -> list:
        candidates = []
        seen: set[str] = set()
        tokens = [
            token
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", query)
            if len(token) >= 4
        ]
        for token in tokens:
            for memory in self.storage.search_fts_global(
                token,
                space,
                limit=limit,
                layer=layer,
                tags=tags,
            ):
                if memory.id in seen:
                    continue
                seen.add(memory.id)
                candidates.append(memory)
        return candidates[:limit]

    def _prepare_results(
        self, memories: list, *, query: str
    ) -> tuple[list[dict], list[dict]]:
        ordered = self._prioritize_verified_conflicts(memories, query)
        results = [memory.to_dict() for memory in ordered]
        for result, memory in zip(results, ordered, strict=False):
            result["verified"] = self._is_verified(memory.to_dict())
            result["conflict_role"] = self._fact_polarity(memory.content)
            result["source_projects"] = self.storage.source_projects(memory.id)
        conflicts = self._detect_conflicts_in_dicts(results, query=query)
        return results, conflicts

    def _prioritize_verified_conflicts(self, memories: list, query: str) -> list:
        conflict_entities = self._conflict_entities(
            [m.to_dict() for m in memories], query
        )

        def priority(memory) -> tuple:
            data = memory.to_dict()
            entity_hit = bool(conflict_entities & _entities(data.get("content", "")))
            verified = self._is_verified(data)
            polarity = self._fact_polarity(data.get("content", ""))
            verified_negative = verified and polarity == "negative" and entity_hit
            return (
                1 if verified_negative else 0,
                1 if verified and entity_hit else 0,
                memory.importance,
                memory.score,
                memory.updated_at,
            )

        return sorted(memories, key=priority, reverse=True)

    def _detect_conflicts(self, content: str, tags: list, meta: dict) -> list[dict]:
        entities = _entities(content)
        polarity = self._fact_polarity(content)
        if not entities or polarity == "unknown":
            return []
        rows = []
        for entity in entities:
            for item in self.storage.search_graph(self.space, entity, limit=10):
                memory = item.get("memory") if isinstance(item, dict) else None
                if isinstance(memory, dict):
                    rows.append(memory)
        new_memory = {
            "id": None,
            "content": content,
            "tags": tags,
            "meta": meta,
            "importance": 0,
            "score": 0,
        }
        return self._detect_conflicts_in_dicts([new_memory, *rows], query=content)

    def _detect_conflicts_in_dicts(
        self, memories: list[dict], *, query: str
    ) -> list[dict]:
        conflicts = []
        seen: set[tuple[str, str]] = set()
        for entity in self._conflict_entities(memories, query):
            negative = []
            positive = []
            for memory in memories:
                content = memory.get("content", "")
                if entity not in _entities(content):
                    continue
                polarity = self._fact_polarity(content)
                if polarity == "negative":
                    negative.append(memory)
                elif polarity == "positive":
                    positive.append(memory)
            if not negative or not positive:
                continue
            pair_key = (
                entity,
                ",".join(sorted(str(m.get("id")) for m in negative + positive)),
            )
            if pair_key in seen:
                continue
            seen.add(pair_key)
            conflicts.append(
                {
                    "entity": entity,
                    "type": "code_fact_contradiction",
                    "negative": [_conflict_item(item) for item in negative],
                    "positive": [_conflict_item(item) for item in positive],
                    "verified_negative": any(
                        self._is_verified(item) for item in negative
                    ),
                    "suggestion": "Prefer codebase-verified negative facts; review and forget stale positive memories.",
                }
            )
        return conflicts

    def _conflict_entities(self, memories: list[dict], query: str) -> set[str]:
        entity_to_polarities: dict[str, set[str]] = {}
        for memory in memories:
            content = memory.get("content", "")
            polarity = self._fact_polarity(content)
            if polarity == "unknown":
                continue
            for entity in _entities(content):
                entity_to_polarities.setdefault(entity, set()).add(polarity)
        return {
            entity
            for entity, polarities in entity_to_polarities.items()
            if {"positive", "negative"}.issubset(polarities)
        }

    @staticmethod
    def _fact_polarity(content: str) -> str:
        lower = f" {content.lower()} "
        if any(pattern in lower for pattern in NEGATION_PATTERNS):
            return "negative"
        if any(pattern in lower for pattern in AFFIRMATION_PATTERNS):
            return "positive"
        return "unknown"

    @staticmethod
    def _is_verified(memory: dict) -> bool:
        tags = set(memory.get("tags") or [])
        meta = memory.get("meta") or {}
        content = str(memory.get("content", "")).lower()
        return (
            bool(tags & VERIFIED_TAGS)
            or meta.get("source") == "codebase"
            or bool(meta.get("verified_at"))
            or "[pipeline]" in content
        )

    @staticmethod
    def _forget_suggestions(conflicts: list[dict]) -> list[dict]:
        suggestions = []
        for conflict in conflicts:
            if not conflict.get("verified_negative"):
                continue
            for item in conflict.get("positive", []):
                memory_id = item.get("id")
                if memory_id:
                    suggestions.append(
                        {
                            "id": memory_id,
                            "reason": f"Conflicts with codebase-verified fact about {conflict['entity']}",
                            "entity": conflict["entity"],
                        }
                    )
        return suggestions


def _entities(content: str) -> set[str]:
    return {
        match.group(0).replace("\\", "/")
        for match in ENTITY_PATTERN.finditer(content or "")
    }


def _conflict_item(memory: dict) -> dict:
    return {
        "id": memory.get("id"),
        "content": memory.get("content"),
        "score": memory.get("score"),
        "importance": memory.get("importance"),
        "tags": memory.get("tags", []),
        "verified": MemoryService._is_verified(memory),
    }
