from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from urllib import error

import pytest

from evermind_mcp.api_client import ApiResult, post_json
from evermind_mcp.config_v2 import EverMindConfig, load_config
from evermind_mcp.embedding import EncodedEmbedding, EmbeddingManager, EmbeddingProfile
from evermind_mcp.memory_service_v2 import MemoryService, _detect_memory_type
from evermind_mcp.reranker import RerankerManager
from evermind_mcp.storage import EmbeddedStorage


def test_api_client_classifies_timeout(monkeypatch):
    def fail_timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("evermind_mcp.api_client.request.urlopen", fail_timeout)
    result = post_json(
        url="https://example.invalid/v1/embeddings",
        api_key="sk-test",
        payload={"model": "test"},
        timeout=0.01,
        purpose="test",
    )
    assert result.ok is False
    assert result.error_type == "timeout"
    assert result.latency_ms >= 0


def test_api_client_classifies_http_error(monkeypatch):
    def fail_http(*args, **kwargs):
        raise error.HTTPError(
            url="https://example.invalid",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("evermind_mcp.api_client.request.urlopen", fail_http)
    result = post_json(
        url="https://example.invalid/v1/rerank",
        api_key="sk-test",
        payload={"model": "test"},
        timeout=1,
        purpose="test",
    )
    assert result.ok is False
    assert result.error_type == "http_error"
    assert result.status_code == 429


def test_load_config_reads_repo_root_env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    mcp_dir = repo / "mcp"
    mcp_dir.mkdir(parents=True)
    (repo / ".env").write_text(
        "\n".join(
            [
                "EVERMIND_SILICONFLOW_API_KEY=sk-test-local-only",
                "EVERMIND_EMBED_PROVIDER=siliconflow",
                "EVERMIND_EMBED_MODEL=Qwen/Qwen3-Embedding-8B",
                "EVERMIND_RERANK_MODEL=Qwen/Qwen3-Reranker-8B",
                "EVERMIND_LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(mcp_dir)
    cfg = load_config(str(mcp_dir))
    assert cfg.siliconflow_api_key == "sk-test-local-only"
    assert cfg.embed_provider == "siliconflow"
    assert cfg.embed_model == "Qwen/Qwen3-Embedding-8B"
    assert cfg.rerank_model == "Qwen/Qwen3-Reranker-8B"
    assert cfg.llm_model == "deepseek-ai/DeepSeek-V4-Flash"


def test_qwen_default_without_key_uses_bundled_local_profile():
    local_model = (
        Path(__file__).resolve().parents[2]
        / "third_party"
        / "models"
        / "multilingual-e5-small"
    )
    manager = EmbeddingManager(
        model_name="Qwen/Qwen3-Embedding-8B",
        provider="auto",
        api_key="",
        enabled=True,
        local_model_path=local_model,
    )
    try:
        assert manager.available is True
        assert manager.local_profile.provider == "local"
        assert manager.local_profile.dimensions == 384
    finally:
        manager.close()


def test_external_embedding_failure_falls_back_to_local(tmp_path, monkeypatch):
    manager = EmbeddingManager(
        model_name="external-model",
        provider="auto",
        api_key="sk-test",
        enabled=True,
        local_model_path=tmp_path,
    )
    monkeypatch.setattr(manager, "_encode_api", lambda _text: None)
    monkeypatch.setattr(
        manager,
        "_encode_local",
        lambda _text, *, query: [1.0] + [0.0] * 383,
    )
    try:
        encoded = manager.encode_query("semantic query")
        assert encoded is not None
        assert encoded.profile.provider == "local"
        assert encoded.fallback_reason == "external_unavailable"
    finally:
        manager.close()


def test_external_embedding_is_preferred_when_healthy(tmp_path, monkeypatch):
    manager = EmbeddingManager(
        model_name="external-model",
        provider="auto",
        api_key="sk-test",
        enabled=True,
        local_model_path=tmp_path,
        dimensions=3,
    )
    monkeypatch.setattr(manager, "_encode_api", lambda _text: [0.0, 1.0, 0.0])
    monkeypatch.setattr(
        manager,
        "_encode_local",
        lambda _text, *, query: pytest.fail("local fallback should not run"),
    )
    try:
        encoded = manager.encode_query("semantic query")
        assert encoded is not None
        assert encoded.profile.provider == "siliconflow"
        assert encoded.fallback_reason is None
    finally:
        manager.close()


def test_embedding_profiles_are_stored_and_searched_without_mixing(tmp_path):
    storage = EmbeddedStorage(tmp_path / "catalog.db")
    try:
        local = storage.insert_memory("project-a", "local profile target", importance=1)
        external = storage.insert_memory(
            "project-a", "external profile target", importance=1
        )
        storage.register_embedding_profile("local-v1", "local", "e5", "rev", 3)
        storage.register_embedding_profile(
            "external-v1", "siliconflow", "qwen", "v1", 3
        )
        storage.store_profile_embedding(local.id, "local-v1", [1.0, 0.0, 0.0])
        storage.store_profile_embedding(
            external.id, "external-v1", [1.0, 0.0, 0.0]
        )

        results = storage.search_profile_embeddings(
            [1.0, 0.0, 0.0], "local-v1", "project-a", limit=5
        )

        assert [item.id for item in results] == [local.id]
    finally:
        storage.close_all()


def test_pending_local_embedding_survives_storage_restart(tmp_path):
    path = tmp_path / "catalog.db"
    storage = EmbeddedStorage(path)
    memory = storage.insert_memory("project-a", "pending local vector", importance=1)
    storage.register_embedding_profile("local-v1", "local", "e5", "rev", 3)
    storage.mark_embedding_pending(memory.id, "local-v1")
    storage.close_all()

    reopened = EmbeddedStorage(path)
    try:
        assert reopened.pending_embedding_inputs("local-v1") == [
            (memory.id, memory.content)
        ]
    finally:
        reopened.close_all()


@pytest.mark.asyncio
async def test_memory_service_uses_profile_vectors_for_semantic_recall(
    tmp_path, monkeypatch
):
    profile = EmbeddingProfile("local-test", "local", "test", "v1", 3)

    class FakeEmbeddingManager:
        def __init__(self, **_kwargs):
            self.local_profile = profile
            self.external_profile = None
            self.profiles = (profile,)
            self.available = True
            self.dim = 3
            self.provider = "local"
            self.queue_size = 0
            self.processed_count = 0
            self.failed_count = 0
            self.last_selected_profile = profile.profile_id
            self.last_fallback_reason = None
            self.last_latency_ms = 0.1
            self._callback = None

        def set_callback(self, callback):
            self._callback = callback

        def enqueue(self, memory_id, text, profile_id=None):
            assert profile_id in (None, profile.profile_id)
            vector = [1.0, 0.0, 0.0] if "Parquet" in text else [0.0, 1.0, 0.0]
            self._callback(memory_id, profile, vector)
            self.processed_count += 1

        def encode(self, _text):
            return [1.0, 0.0, 0.0]

        def encode_query(self, _text):
            return EncodedEmbedding([1.0, 0.0, 0.0], profile)

        def encode_local_query(self, _text):
            return self.encode_query(_text)

        def metrics_snapshot(self):
            return {}

        def warmup(self):
            return True

        def close(self):
            return None

        @staticmethod
        def cosine_similarity(_left, _right):
            return 0.0

    monkeypatch.setattr(
        "evermind_mcp.memory_service_v2.EmbeddingManager", FakeEmbeddingManager
    )
    service = MemoryService(
        EverMindConfig(
            home=tmp_path,
            default_space="coding:test",
            embed_enabled=True,
            embed_warmup_on_start=False,
            rerank_enabled=False,
            cosine_dedup_threshold=0,
        )
    )
    try:
        target = await service.remember(
            "Invoice exports are written as Parquet files.", importance=1
        )
        await service.remember(
            "Authentication tokens rotate every seven days.", importance=1
        )

        recalled = await service.recall(
            "Which format does billing data use?", mode="semantic", limit=1
        )

        assert recalled["results"][0]["id"] == target["id"]
        assert recalled["embedding_profile"] == profile.profile_id
        assert service.storage.count_profile_embeddings(profile.profile_id) == 2
        status = await service.status()
        assert status["embedding_profiles"] == [
            {
                "profile_id": profile.profile_id,
                "provider": "local",
                "model": "test",
                "version": "v1",
                "dimensions": 3,
                "coverage": 1.0,
                "ready": 2,
            }
        ]
    finally:
        service.close()


@pytest.mark.asyncio
async def test_incomplete_external_coverage_uses_local_baseline(
    tmp_path, monkeypatch
):
    service = MemoryService(
        EverMindConfig(
            home=tmp_path,
            default_space="coding:test",
            siliconflow_api_key="sk-test",
            embed_provider="auto",
            embed_model="external-model",
            embed_dim=3,
            local_embed_model_path=tmp_path / "missing-model",
            embed_warmup_on_start=False,
            rerank_enabled=False,
            graph_enabled=False,
        )
    )
    try:
        local = service.embedder.local_profile
        external = service.embedder.external_profile
        assert external is not None

        local_target = service.storage.insert_memory(
            service.space, "Billing exports use Parquet files.", importance=1
        )
        external_only = service.storage.insert_memory(
            service.space, "Authentication tokens rotate weekly.", importance=1
        )
        local_vector = [1.0] + [0.0] * (local.dimensions - 1)
        external_vector = [1.0, 0.0, 0.0]
        service.storage.store_profile_embedding(
            local_target.id, local.profile_id, local_vector
        )
        service.storage.store_profile_embedding(
            external_only.id, external.profile_id, external_vector
        )
        monkeypatch.setattr(
            service.embedder,
            "encode_query",
            lambda _text: EncodedEmbedding(external_vector, external),
        )
        monkeypatch.setattr(
            service.embedder,
            "encode_local_query",
            lambda _text: EncodedEmbedding(local_vector, local),
        )

        recalled = await service.recall(
            "Which format does billing use?", mode="semantic", limit=1, min_score=0
        )
        status = await service.status()
        health = await service.health()

        assert recalled["results"][0]["id"] == local_target.id
        assert recalled["embedding_profile"] == local.profile_id
        assert recalled["embedding_coverage"] == 0.5
        assert (
            recalled["embedding_fallback_reason"]
            == "external_coverage_incomplete"
        )
        assert status["embeddings_stored_count"] == 1
        assert status["embedding_coverage_percent"] == 50.0
        assert health["embedding_coverage_percent"] == 50.0
    finally:
        service.close()


def test_reranker_parses_siliconflow_response():
    candidates = [
        type("Row", (), {"id": "a", "content": "first", "score": 0.0})(),
        type("Row", (), {"id": "b", "content": "second", "score": 0.0})(),
    ]
    parsed = RerankerManager._parse_results(
        {
            "results": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.1},
            ]
        },
        candidates,
    )
    assert [item[0].id for item in parsed] == ["b", "a"]


def test_reranker_api_failure_falls_back_without_applied_flag(monkeypatch):
    monkeypatch.setattr(
        "evermind_mcp.reranker.post_json",
        lambda **kwargs: ApiResult(
            ok=False,
            data=None,
            latency_ms=12.3,
            error_type="timeout",
            error_message="timed out",
        ),
    )
    manager = RerankerManager(api_key="sk-test", enabled=True)
    candidates = [
        type("Row", (), {"id": "a", "content": "first", "score": 0.0})(),
        type("Row", (), {"id": "b", "content": "second", "score": 0.0})(),
    ]

    result = manager.rerank("query", candidates, top_k=1)

    assert [item.id for item in result] == ["a"]
    assert manager.last_applied is False
    assert manager.last_fallback_reason == "timeout"
    assert manager.metrics_snapshot()["timeout_count"] == 1


@pytest.mark.asyncio
async def test_recall_applies_rerank_when_available(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
    )
    svc = MemoryService(cfg)

    class FakeReranker:
        available = True
        last_scores = [{"id": "placeholder", "score": 1.0}]

        def rerank(self, query, candidates, *, top_k):
            ordered = sorted(candidates, key=lambda m: "target" not in m.content)
            for idx, memory in enumerate(ordered):
                memory.score = 1.0 - idx * 0.1
            return ordered[:top_k]

    svc.reranker = FakeReranker()
    await svc.remember("auth generic memory", importance=1)
    await svc.remember("auth target memory", importance=1)

    result = await svc.recall("auth", limit=1)
    assert result["mode"] == "fts+rerank"
    assert result["results"][0]["content"] == "auth target memory"


@pytest.mark.asyncio
async def test_recall_rerank_timeout_is_observable_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "evermind_mcp.reranker.post_json",
        lambda **kwargs: ApiResult(
            ok=False,
            data=None,
            latency_ms=30_001.0,
            error_type="timeout",
            error_message="timed out",
        ),
    )
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=True,
        siliconflow_api_key="sk-test",
    )
    svc = MemoryService(cfg)
    await svc.remember("auth first memory", importance=1)
    await svc.remember("auth second memory", importance=1)

    result = await svc.recall("auth", limit=1)
    health = await svc.health()

    assert result["mode"] == "fts"
    assert result["rerank_applied"] is False
    assert result["rerank_fallback_reason"] == "timeout"
    assert health["rerank_api_metrics"]["timeout_count"] >= 1
    assert health["last_recall_trace"]["rerank_fallback_reason"] == "timeout"


@pytest.mark.asyncio
async def test_recall_filters_results_below_min_score(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
        recall_min_score=0.15,
    )
    svc = MemoryService(cfg)
    await svc.remember("auth first memory", importance=1)
    await svc.remember("auth second memory", importance=1)

    result = await svc.recall("auth", limit=5, min_score=0.99)
    health = await svc.health()

    assert result["results"] == []
    assert result["count"] == 0
    assert result["threshold_reason"] == "below_threshold"
    assert health["last_recall_trace"]["threshold_reason"] == "below_threshold"


@pytest.mark.asyncio
async def test_recall_min_score_zero_disables_threshold_filter(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
        recall_min_score=0.15,
    )
    svc = MemoryService(cfg)
    await svc.remember("auth first memory", importance=1)

    result = await svc.recall("auth", limit=5, min_score=0)

    assert result["count"] == 1
    assert result["threshold_reason"] is None


@pytest.mark.asyncio
async def test_reindex_restores_missing_fts_entries(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
    )
    svc = MemoryService(cfg)
    await svc.remember("YouTube 发布流程 使用 aria role", importance=1)
    svc.storage.conn.execute("DELETE FROM memories_fts")
    svc.storage.conn.commit()
    assert (await svc.recall("YouTube"))["count"] == 0

    result = await svc.reindex()
    assert result["reindexed"] == 1
    assert result["graph_reindexed"] == 1
    assert (await svc.recall("YouTube"))["count"] == 1


def test_graph_entity_extraction_covers_paths_terms_and_chinese(tmp_path):
    storage = EmbeddedStorage(tmp_path / "graph-extract.db")
    entities = storage.extract_entities_from_content(
        "Bug: farming runner 并发时 Playwright sync API 抛 greenlet 错误；"
        "publish/service.py 发布流程 使用 pytest，禁止文本选择器。"
    )
    assert "greenlet" in entities
    assert "playwright" in entities
    assert "pytest" in entities
    assert "publish/service.py" in entities
    assert "service.py" in entities
    assert "发布流程" in entities
    assert "文本选择器" in entities


@pytest.mark.asyncio
async def test_reindex_rebuilds_graph_for_concept_and_file(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
    )
    svc = MemoryService(cfg)
    await svc.remember(
        "Bug: farming runner 并发时 Playwright sync API 抛 greenlet 错误；"
        "publish/service.py 发布流程 必须用 aria role。",
        importance=1,
    )
    svc.storage.conn.execute("DELETE FROM graph_edges")
    svc.storage.conn.execute("DELETE FROM graph_nodes")
    svc.storage.conn.commit()
    assert (await svc.graph_explore("greenlet"))["count"] == 0

    result = await svc.reindex()
    by_concept = await svc.graph_explore("greenlet")
    by_file = await svc.graph_explore("publish/service.py")

    assert result["graph_linked_memories"] == 1
    assert by_concept["count"] == 1
    assert by_file["count"] == 1


@pytest.mark.asyncio
async def test_remember_rejects_sensitive_content(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
    )
    svc = MemoryService(cfg)
    result = await svc.remember("api key sk-proj-abcdefghijklmnopqrstuvwxyz1234567890abcdef")
    assert result["action"] == "rejected"
    assert result["error"] == "sensitive_content"
    assert (await svc.status())["total_count"] == 0


@pytest.mark.asyncio
async def test_health_reports_index_and_model_metrics(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
    )
    svc = MemoryService(cfg)
    await svc.remember("health memory", importance=1)
    health = await svc.health()
    assert health["total_count"] == 1
    assert health["fts_index_health"] == "ok"
    assert "embedding_queue_pending" in health
    assert "embedding_api_metrics" in health
    assert "rerank_api_metrics" in health
    assert "graph_node_count" in health
    assert "recall_latency_metrics" in health


def test_chinese_procedural_detection():
    assert _detect_memory_type("如何运行 pytest 测试命令", 1) == "procedural"


def test_sqlite_vec_loaded_for_background_thread_connections(tmp_path):
    storage = EmbeddedStorage(tmp_path / "vec-thread.db")
    if not storage._vec_available:
        pytest.skip("sqlite-vec not installed")
    memory = storage.insert_memory(
        space="coding:test",
        content="threaded embedding update",
        layer="semantic",
    )
    rowid = storage.get_memory_rowid(memory.id)
    assert rowid is not None
    errors: list[Exception] = []

    def update_in_thread():
        try:
            storage.update_embedding(rowid, [0.0] * 512)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    thread = threading.Thread(target=update_in_thread)
    thread.start()
    thread.join(timeout=5)
    assert errors == []
    row = storage.conn.execute(
        "SELECT embedding_ready FROM memories WHERE id=?",
        (memory.id,),
    ).fetchone()
    assert row["embedding_ready"] == 1
    storage.close_all()


@pytest.mark.asyncio
async def test_fastmcp_dispatch_forget_reindex_health_list_spaces(tmp_path, monkeypatch):
    import evermind_mcp.server_v2 as server_mod

    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
    )
    svc = MemoryService(cfg)
    server_mod._svc = svc
    monkeypatch.setattr(
        server_mod, "_maybe_update_space_from_roots", lambda _context=None: asyncio.sleep(0)
    )

    remembered = (
        await server_mod.mcp.call_tool("remember", {"content": "delete me"})
    ).structured_content
    forgotten = (
        await server_mod.mcp.call_tool("forget", {"id": remembered["id"]})
    ).structured_content
    assert forgotten["deleted"] is True

    for tool_name in ("reindex", "health", "list_spaces"):
        payload = (await server_mod.mcp.call_tool(tool_name, {})).structured_content
        assert "error" not in payload

    server_mod._svc = None


@pytest.mark.asyncio
async def test_fastmcp_briefing_defaults_to_fast(tmp_path, monkeypatch):
    import evermind_mcp.server_v2 as server_mod

    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
        llm_enabled=True,
        llm_briefing_summary=True,
        siliconflow_api_key="sk-test",
    )
    svc = MemoryService(cfg)
    called = False

    def fail_if_called(memories):
        nonlocal called
        called = True
        return "should not be used"

    svc.llm.summarize_briefing = fail_if_called
    server_mod._svc = svc
    monkeypatch.setattr(
        server_mod, "_maybe_update_space_from_roots", lambda _context=None: asyncio.sleep(0)
    )

    payload = (await server_mod.mcp.call_tool("briefing", {})).structured_content

    assert payload["fast"] is True
    assert called is False
    server_mod._svc = None


@pytest.mark.asyncio
async def test_briefing_fast_false_keeps_llm_summary_path(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
        llm_enabled=True,
        llm_briefing_summary=True,
        siliconflow_api_key="sk-test",
    )
    svc = MemoryService(cfg)
    await svc.remember("Decision: use role based selectors", importance=2)
    svc.llm.summarize_briefing = lambda memories: "LLM summary"

    result = await svc.briefing(fast=False)

    assert result["fast"] is False
    assert result["context_summary"] == "LLM summary"
