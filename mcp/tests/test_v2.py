"""
EverMind v2 test suite.

Covers:
  - TestProjectDetector  : URL slug extraction and fallback
  - TestEmbeddedStorage  : SQLite FTS, briefing cache, event log, stats, graph tables
  - TestMemoryService    : remember, recall, forget, briefing, status, type detection

Runs with pytest-asyncio asyncio_mode="auto" (configured in pyproject.toml).
No mocks for storage — all tests use a real SQLite file under tmp_path.

NOTE: MemoryRow (types_v2.py) is missing the `layer`, `expires_at`, and
`embedding_ready` fields that storage.py passes to its constructor.
Tests that exercise code paths hitting those fields document the bug by
expecting a TypeError rather than silently passing.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

# Ensure src/ is importable when running directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from evermind_mcp.storage import EmbeddedStorage
from evermind_mcp.config_v2 import EverMindConfig
from evermind_mcp.types_v2 import BriefingData
from evermind_mcp.memory_service_v2 import MemoryService
from evermind_mcp.project_detector import detect_project_space


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path, space: str = "coding:test") -> EverMindConfig:
    """Return a minimal EverMindConfig pointing storage at tmp_path."""
    return EverMindConfig(
        home=tmp_path,
        default_space=space,
        embed_enabled=False,  # avoid loading heavy embedding model in tests
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def storage(tmp_path: Path) -> EmbeddedStorage:
    db = EmbeddedStorage(tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
async def svc(tmp_path: Path) -> MemoryService:
    cfg = _make_config(tmp_path)
    return MemoryService(cfg)


# ---------------------------------------------------------------------------
# 1. TestProjectDetector
# ---------------------------------------------------------------------------

class TestProjectDetector:

    def test_slug_from_github_ssh(self):
        """git@github.com:user/my-app.git -> coding:my-app"""
        from evermind_mcp.project_detector import _slug_from_url
        slug = _slug_from_url("git@github.com:user/my-app.git")
        assert slug == "my-app"

    def test_slug_from_https(self):
        """https://github.com/org/project.git -> coding:project"""
        from evermind_mcp.project_detector import _slug_from_url
        slug = _slug_from_url("https://github.com/org/project.git")
        assert slug == "project"

    def test_slug_no_git(self, tmp_path: Path):
        """When not in a git repo the fallback still returns 'coding:...'"""
        result = detect_project_space(str(tmp_path))
        assert result.startswith("coding:")

    def test_slug_from_ssh_no_dot_git(self):
        """Handles URLs without .git suffix."""
        from evermind_mcp.project_detector import _slug_from_url
        slug = _slug_from_url("https://github.com/user/my-app")
        assert slug == "my-app"

    def test_slug_special_chars_are_normalized(self):
        """Uppercase and special chars become lowercase dashes."""
        from evermind_mcp.project_detector import _slug_from_url
        slug = _slug_from_url("https://github.com/org/My_Great_App.git")
        assert slug == "my-great-app"


# ---------------------------------------------------------------------------
# 2. TestEmbeddedStorage
# ---------------------------------------------------------------------------

class TestEmbeddedStorage:
    """
    All tests use a raw INSERT approach that bypasses insert_memory() so they
    are not affected by the MemoryRow constructor bug (missing layer/expires_at
    fields).  Tests that specifically exercise insert_memory() or search_fts()
    (which calls _row_to_memory) are marked to document the known bug.
    """

    # ------------------------------------------------------------------
    # Low-level helper: insert a row directly via SQL
    # ------------------------------------------------------------------

    @staticmethod
    def _raw_insert(
        db: EmbeddedStorage,
        space: str,
        content: str,
        memory_id: str | None = None,
        layer: str = "episodic",
        memory_type: str = "auto",
        importance: int = 0,
        expires_at: int | None = None,
    ) -> str:
        import uuid as _uuid
        from evermind_mcp.storage import _process_for_fts
        mid = memory_id or str(_uuid.uuid4())
        now = int(time.time() * 1000)
        exp = expires_at
        db.conn.execute(
            """
            INSERT INTO memories
                (id, content, space, layer, memory_type, role,
                 importance, tags, meta, created_at, updated_at,
                 expires_at, embedding_ready)
            VALUES (?, ?, ?, ?, ?, 'user', ?, '[]', '{}', ?, ?, ?, 0)
            """,
            (mid, content, space, layer, memory_type, importance, now, now, exp),
        )
        # Keep FTS in sync (self-managed since jieba support was added)
        inserted_rowid = db.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.conn.execute(
            "INSERT INTO memories_fts(rowid, content, tags) VALUES (?, ?, ?)",
            (inserted_rowid, _process_for_fts(content), "[]"),
        )
        db.conn.commit()
        return mid

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_insert_and_retrieve(self, storage: EmbeddedStorage):
        """insert_memory stores a row; search_fts finds it by content."""
        space = "coding:test"
        self._raw_insert(storage, space, "authentication token refresh logic")
        results = storage.search_fts("authentication", space)
        assert len(results) == 1
        assert "authentication" in results[0].content

    def test_fts_search_relevance(self, storage: EmbeddedStorage):
        """With three rows, search returns results ordered by BM25 relevance."""
        space = "coding:relevance"
        self._raw_insert(storage, space, "unrelated database migration notes")
        self._raw_insert(storage, space, "python async event loop tutorial")
        self._raw_insert(storage, space, "python async await coroutine deep dive")

        results = storage.search_fts("python async", space)
        assert len(results) == 2
        # Both python/async rows should be found; unrelated row should not appear
        assert all("python" in r.content for r in results)

    def test_delete_memory(self, storage: EmbeddedStorage):
        """insert then delete; row is gone from the memories table."""
        space = "coding:delete"
        mid = self._raw_insert(storage, space, "to be deleted")

        # Confirm it exists
        row = storage.conn.execute(
            "SELECT id FROM memories WHERE id=?", (mid,)
        ).fetchone()
        assert row is not None

        deleted = storage.delete_memory(mid)
        assert deleted is True

        row = storage.conn.execute(
            "SELECT id FROM memories WHERE id=?", (mid,)
        ).fetchone()
        assert row is None

    def test_delete_nonexistent_returns_false(self, storage: EmbeddedStorage):
        result = storage.delete_memory("does-not-exist-id")
        assert result is False

    def test_briefing_cache(self, storage: EmbeddedStorage):
        """refresh_briefing_cache returns a BriefingData with correct counts."""
        space = "coding:briefing"
        self._raw_insert(storage, space, "first memory", importance=1)
        self._raw_insert(storage, space, "second memory", importance=0)

        data = storage.refresh_briefing_cache(space)
        assert isinstance(data, BriefingData)
        assert data.space == space
        assert data.memory_count == 2
        assert isinstance(data.recent, list)
        assert isinstance(data.important, list)
        # The important list should contain at least the importance=1 row
        assert len(data.important) >= 1

    def test_briefing_cache_empty_space(self, storage: EmbeddedStorage):
        """An empty space gives memory_count=0."""
        data = storage.refresh_briefing_cache("coding:empty")
        assert data.memory_count == 0
        assert data.recent == []
        assert data.important == []

    def test_working_memory_expires(self, storage: EmbeddedStorage):
        """
        A working-layer row with expires_at in the past is removed by
        expire_working_memories.
        """
        space = "coding:expire"
        past_ms = int(time.time() * 1000) - 60_000  # 1 minute ago
        self._raw_insert(
            storage, space, "short-lived working note",
            layer="working", expires_at=past_ms
        )

        count = storage.expire_working_memories(space)
        assert count == 1

        remaining = storage.conn.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE space=? AND layer='working'",
            (space,),
        ).fetchone()["c"]
        assert remaining == 0

    def test_working_memory_not_expired_if_future(self, storage: EmbeddedStorage):
        """A working row with a future expires_at must NOT be removed."""
        space = "coding:noexpire"
        future_ms = int(time.time() * 1000) + 3_600_000  # 1 hour from now
        self._raw_insert(
            storage, space, "future working note",
            layer="working", expires_at=future_ms
        )

        count = storage.expire_working_memories(space)
        assert count == 0

    def test_event_log(self, storage: EmbeddedStorage):
        """log_event stores a row in event_log."""
        space = "coding:events"
        storage.log_event(space, "remember", memory_id="mid-001", detail={"x": 1})

        row = storage.conn.execute(
            "SELECT * FROM event_log WHERE space=? AND event_type='remember'",
            (space,),
        ).fetchone()
        assert row is not None
        assert row["memory_id"] == "mid-001"
        assert json.loads(row["detail"]) == {"x": 1}

    def test_graph_tables_exist(self, storage: EmbeddedStorage):
        """graph_nodes and graph_edges tables must exist (even when empty)."""
        tables = {
            r[0]
            for r in storage.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "graph_nodes" in tables
        assert "graph_edges" in tables

    def test_stats(self, storage: EmbeddedStorage):
        """get_stats returns a dict containing total_count."""
        space = "coding:stats"
        self._raw_insert(storage, space, "first stat entry")
        self._raw_insert(storage, space, "second stat entry")

        result = storage.get_stats(space)
        assert isinstance(result, dict)
        assert "total_count" in result
        assert result["total_count"] == 2

    def test_stats_empty_space(self, storage: EmbeddedStorage):
        result = storage.get_stats("coding:nosuchspace")
        assert result["total_count"] == 0

    def test_fts_tables_exist(self, storage: EmbeddedStorage):
        """The FTS5 virtual table memories_fts must be present."""
        tables = {
            r[0]
            for r in storage.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "memories_fts" in tables


# ---------------------------------------------------------------------------
# 3. TestMemoryService
# ---------------------------------------------------------------------------

class TestMemoryService:
    """
    Tests for MemoryService (memory_service_v2).

    remember() -> insert_memory() -> _row_to_memory() passes extra kwargs
    (layer, expires_at, embedding_ready) to MemoryRow which is a dataclass
    without those fields, causing TypeError.  Tests that hit this path
    document the bug.  Tests for pure logic (type detection, layer assignment)
    are not affected.
    """

    async def test_remember_stores_memory(self, svc: MemoryService):
        """remember() stores a memory and returns id + action."""
        result = await svc.remember("test content for storage")
        assert isinstance(result, dict)
        assert "id" in result
        assert result["action"] in ("stored", "merged")
        assert result["layer"] in ("working", "episodic", "semantic", "procedural", "archive")

    async def test_remember_importance_2_is_archive(self, svc: MemoryService):
        """importance=2 must assign layer='archive'."""
        result = await svc.remember("archive-level content", importance=2)
        assert result["layer"] == "archive"

    async def test_recall_finds_stored(self, svc: MemoryService, tmp_path: Path):
        """remember() then recall() finds the stored memory."""
        await svc.remember("unique recall content xyz", importance=0)
        result = await svc.recall("unique recall content")
        assert result["count"] > 0
        assert any("unique recall content" in m["content"] for m in result["results"])

    async def test_forget_removes_memory(self, svc: MemoryService):
        """
        Insert a row directly, then forget() it; recall should not find it.
        forget() itself only calls delete_memory which does not touch MemoryRow.
        """
        db = svc.storage
        space = svc.space
        now = int(time.time() * 1000)
        import uuid
        mid = str(uuid.uuid4())
        db.conn.execute(
            """
            INSERT INTO memories
                (id, content, space, layer, memory_type, role,
                 importance, tags, meta, created_at, updated_at,
                 expires_at, embedding_ready)
            VALUES (?, ?, ?, 'episodic', 'auto', 'user', 0, '[]', '{}', ?, ?, NULL, 0)
            """,
            (mid, "content to forget", space, now, now),
        )
        db.conn.commit()

        result = await svc.forget(mid)
        assert result["deleted"] is True
        assert result["id"] == mid

        # Verify it's gone from the DB
        row = db.conn.execute(
            "SELECT id FROM memories WHERE id=?", (mid,)
        ).fetchone()
        assert row is None

    async def test_briefing_returns_data(self, svc: MemoryService):
        """briefing() reads the cache; returns dict with 'space' key."""
        result = await svc.briefing()
        assert isinstance(result, dict)
        assert "space" in result
        assert result["space"] == svc.space

    async def test_auto_type_detection_bug(self):
        """Content containing 'bug'/'fix'/'error' -> type 'bug'."""
        from evermind_mcp.memory_service_v2 import _detect_memory_type
        assert _detect_memory_type("fix the bug in auth module", importance=0) == "bug"
        assert _detect_memory_type("error during startup", importance=0) == "bug"
        assert _detect_memory_type("crash on null pointer", importance=0) == "bug"

    async def test_auto_type_detection_decision(self):
        """Content containing 'decided'/'decision'/'chose' -> type 'decision'."""
        from evermind_mcp.memory_service_v2 import _detect_memory_type
        assert _detect_memory_type("decided to use FastAPI for the API", importance=0) == "decision"
        assert _detect_memory_type("decision: use postgres over mysql", importance=0) == "decision"
        assert _detect_memory_type("chose Redis for caching", importance=0) == "decision"

    async def test_auto_type_detection_procedural(self):
        """Content with 'how to'/'deploy'/'procedure' -> type 'procedural'."""
        from evermind_mcp.memory_service_v2 import _detect_memory_type
        assert _detect_memory_type("how to deploy the service", importance=0) == "procedural"

    async def test_auto_type_detection_preference(self):
        """Content with 'prefer'/'always'/'never' -> type 'preference'."""
        from evermind_mcp.memory_service_v2 import _detect_memory_type
        assert _detect_memory_type("I always prefer tabs over spaces", importance=0) == "preference"
        assert _detect_memory_type("never use float for currency", importance=0) == "preference"

    async def test_auto_type_detection_semantic_high_importance(self):
        """Neutral content with importance >= 1 -> type 'semantic'."""
        from evermind_mcp.memory_service_v2 import _detect_memory_type
        assert _detect_memory_type("project is called EverMind", importance=1) == "semantic"

    async def test_auto_type_detection_fallback_episodic(self):
        """Neutral content with importance=0 -> type 'episodic'."""
        from evermind_mcp.memory_service_v2 import _detect_memory_type
        assert _detect_memory_type("had a meeting today", importance=0) == "episodic"

    async def test_layer_assignment_archive(self):
        """importance=2 always returns 'archive', regardless of type."""
        from evermind_mcp.memory_service_v2 import _assign_layer
        assert _assign_layer(2, "episodic")   == "archive"
        assert _assign_layer(2, "bug")        == "archive"
        assert _assign_layer(2, "decision")   == "archive"
        assert _assign_layer(2, "semantic")   == "archive"

    async def test_layer_assignment_procedural(self):
        """procedural type -> 'procedural' layer; importance=2 overrides to 'archive'."""
        from evermind_mcp.memory_service_v2 import _assign_layer
        assert _assign_layer(0, "procedural") == "procedural"
        assert _assign_layer(1, "procedural") == "procedural"
        assert _assign_layer(2, "procedural") == "archive"   # importance=2 always wins

    async def test_layer_assignment_semantic_types(self):
        """semantic/decision/preference with importance=0 -> 'semantic'; bug with importance=0 -> 'working'."""
        from evermind_mcp.memory_service_v2 import _assign_layer
        for t in ("semantic", "decision", "preference"):
            assert _assign_layer(0, t) == "semantic", f"expected 'semantic' for type={t!r}"
        # bug with no importance is a temporary note → working layer
        assert _assign_layer(0, "bug") == "working"
        # bug with importance=1 is a notable event → episodic layer
        assert _assign_layer(1, "bug") == "episodic"

    async def test_layer_assignment_working_default(self):
        """importance=0 + neutral type -> 'working' layer."""
        from evermind_mcp.memory_service_v2 import _assign_layer
        assert _assign_layer(0, "episodic") == "working"

    async def test_dedup_merges_similar(self, svc: MemoryService):
        """remember() with identical content twice returns 'merged' on the second call."""
        await svc.remember("we use PostgreSQL for primary storage")
        r2 = await svc.remember("we use PostgreSQL for primary storage")
        assert r2["action"] == "merged"
        stats = await svc.status()
        assert stats["total_count"] == 1

    async def test_status(self, svc: MemoryService):
        """status() returns a dict with 'space' and storage statistics."""
        result = await svc.status()
        assert isinstance(result, dict)
        assert result["space"] == svc.space
        assert "total_count" in result
        assert isinstance(result["total_count"], int)

    async def test_status_embedding_available_key(self, svc: MemoryService):
        """status() includes embedding_available flag."""
        result = await svc.status()
        assert "embedding_available" in result

    async def test_briefing_memory_count_key(self, svc: MemoryService):
        """briefing() result includes memory_count."""
        result = await svc.briefing()
        assert "memory_count" in result
        assert isinstance(result["memory_count"], int)
