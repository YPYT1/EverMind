from __future__ import annotations

import asyncio
import json
import threading
from urllib import error

import pytest

from evermind_mcp.api_client import ApiResult, post_json
from evermind_mcp.config_v2 import EverMindConfig, load_config
from evermind_mcp.embedding import EmbeddingManager
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


def test_qwen_default_without_key_does_not_load_local_model():
    manager = EmbeddingManager(
        model_name="Qwen/Qwen3-Embedding-8B",
        provider="auto",
        api_key="",
        enabled=True,
    )
    assert manager.available is False


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
async def test_server_v2_dispatch_forget_reindex_health_list_spaces(tmp_path, monkeypatch):
    import evermind_mcp.server_v2 as server_mod

    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
    )
    svc = MemoryService(cfg)
    server_mod._svc = svc
    monkeypatch.setattr(server_mod, "_maybe_update_space_from_roots", lambda: asyncio.sleep(0))

    remember_text = await server_mod.call_tool("remember", {"content": "delete me"})
    remembered = json.loads(remember_text[0].text)
    forget_text = await server_mod.call_tool("forget", {"id": remembered["id"]})
    forgotten = json.loads(forget_text[0].text)
    assert forgotten["deleted"] is True

    for tool_name in ("reindex", "health", "list_spaces"):
        result_text = await server_mod.call_tool(tool_name, {})
        payload = json.loads(result_text[0].text)
        assert "error" not in payload

    server_mod._svc = None
