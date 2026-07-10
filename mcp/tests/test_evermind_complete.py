"""Comprehensive pytest test suite for EverMind v2 functionality.

Tests all new and existing functionality including FTS boundaries, deduplication,
RRF fusion, graph layer, briefing config, list operations, and embedding dimension protection.
"""

import pytest
import asyncio
import sys

sys.path.insert(0, "src")

from evermind_mcp.storage import EmbeddedStorage
from evermind_mcp.config_v2 import EverMindConfig
from evermind_mcp.memory_service_v2 import MemoryService
from evermind_mcp.project_detector import _slug_from_url


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def storage(tmp_path):
    """Provide a clean EmbeddedStorage instance for each test."""
    s = EmbeddedStorage(tmp_path / "test.db")
    yield s
    s.close_all()


@pytest.fixture
def svc(tmp_path):
    """Provide a MemoryService with embedding disabled for faster tests."""
    cfg = EverMindConfig(
        home=tmp_path, default_space="coding:test", embed_enabled=False
    )
    return MemoryService(cfg)


# ============================================================================
# TestFTSBoundaries - Full-text search edge cases
# ============================================================================


class TestFTSBoundaries:
    """Test FTS5 query handling for special characters and boundary cases."""

    def test_fts_hyphen_in_query(self, storage):
        """Content with hyphens should be searchable with hyphenated queries."""
        storage.insert_memory(
            space="coding:test",
            content="archive-level content is stored here",
            layer="archive",
        )
        results = storage.search_fts("archive-level", "coding:test")
        assert len(results) == 1
        assert "archive-level" in results[0].content

    def test_fts_special_chars(self, storage):
        """Content with special chars (parens, quotes, colons) should be searchable."""
        storage.insert_memory(
            space="coding:test",
            content='The function call: getData("user:123") returns data',
            layer="episodic",
        )
        results = storage.search_fts("getData", "coding:test")
        assert len(results) == 1
        assert "getData" in results[0].content

    @pytest.mark.xfail(
        reason="SQLite unicode61 tokeniser does not index CJK codepoints by default. "
        "Chinese content is stored and retrievable via list_memories(), "
        "but FTS keyword search requires a CJK-aware tokeniser (e.g. jieba). "
        "This is a known limitation documented in troubleshooting.md.",
        strict=True,
    )
    def test_fts_chinese_content(self, storage):
        """Chinese FTS is a known limitation of the unicode61 tokeniser."""
        storage.insert_memory(
            space="coding:test", content="这是一个关于认证模块的记忆", layer="episodic"
        )
        results = storage.search_fts("认", "coding:test")
        assert len(results) == 1

    def test_fts_empty_query(self, storage):
        """Empty query should return empty list, not crash."""
        storage.insert_memory(
            space="coding:test", content="some content", layer="episodic"
        )
        results = storage.search_fts("", "coding:test")
        assert results == []

    def test_fts_single_token(self, storage):
        """Single-word search should work correctly."""
        storage.insert_memory(
            space="coding:test",
            content="authentication module uses JWT tokens",
            layer="episodic",
        )
        results = storage.search_fts("authentication", "coding:test")
        assert len(results) == 1
        assert "authentication" in results[0].content

    def test_fts_layer_filter(self, storage):
        """FTS search with layer filter should return only matching layer."""
        storage.insert_memory(
            space="coding:test", content="episodic memory about auth", layer="episodic"
        )
        storage.insert_memory(
            space="coding:test", content="semantic memory about auth", layer="semantic"
        )
        results = storage.search_fts("auth", "coding:test", layer="episodic")
        assert len(results) == 1
        assert results[0].layer == "episodic"

    def test_fts_tags_filter(self, storage):
        """FTS search with tags filter should return only tagged memories."""
        storage.insert_memory(
            space="coding:test",
            content="auth module with security tag",
            layer="episodic",
            tags=["security", "auth"],
        )
        storage.insert_memory(
            space="coding:test",
            content="auth module with performance tag",
            layer="episodic",
            tags=["performance"],
        )
        results = storage.search_fts("auth", "coding:test", tags=["security"])
        assert len(results) == 1
        assert "security" in results[0].tags


# ============================================================================
# TestDedup - Deduplication logic
# ============================================================================


class TestDedup:
    """Test exact deduplication logic (fuzzy dedup removed in v2)."""

    @pytest.mark.asyncio
    async def test_exact_dedup(self, svc):
        """Same content twice should be merged, returning merged action."""
        content = "The auth module uses JWT for authentication"
        result1 = await svc.remember(content, importance=1)
        assert result1["action"] == "stored"

        result2 = await svc.remember(content, importance=1)
        assert result2["action"] == "merged"
        assert result2["similar_merged"] is True

        # Verify only one memory exists
        listing = await svc.list_memories(limit=50)
        matching = [m for m in listing["memories"] if m["content"] == content]
        assert len(matching) == 1

    @pytest.mark.asyncio
    async def test_no_false_dedup(self, svc):
        """Different content should not be deduplicated."""
        content1 = "The auth module uses JWT"
        content2 = "The database is PostgreSQL"

        result1 = await svc.remember(content1, importance=1)
        result2 = await svc.remember(content2, importance=1)

        assert result1["action"] == "stored"
        assert result2["action"] == "stored"

        # Verify both exist
        listing = await svc.list_memories(limit=50)
        contents = [m["content"] for m in listing["memories"]]
        assert content1 in contents
        assert content2 in contents

    @pytest.mark.asyncio
    async def test_dedup_different_space(self, tmp_path):
        """Same content in different projects should share one canonical memory."""
        cfg1 = EverMindConfig(
            home=tmp_path, default_space="coding:project1", embed_enabled=False
        )
        cfg2 = EverMindConfig(
            home=tmp_path, default_space="coding:project2", embed_enabled=False
        )
        svc1 = MemoryService(cfg1)
        svc2 = MemoryService(cfg2)

        content = "Shared authentication logic"
        result1 = await svc1.remember(content, importance=1)
        result2 = await svc2.remember(content, importance=1)

        assert result1["action"] == "stored"
        assert result2["action"] == "merged"
        assert result1["id"] == result2["id"]
        assert svc1.storage.source_projects(result1["id"]) == [
            "coding:project1",
            "coding:project2",
        ]

    def test_dedup_case_sensitive(self, storage):
        """Normalized exact dedup should ignore casing differences."""
        storage.insert_memory(
            space="coding:test", content="Auth Module", layer="episodic"
        )
        existing = storage.find_exact("auth module", "coding:test")
        assert existing is not None
        assert existing.content == "Auth Module"


# ============================================================================
# TestRRFFusion - Reciprocal Rank Fusion scoring
# ============================================================================


class TestRRFFusion:
    """Test RRF hybrid search fusion logic."""

    @pytest.mark.asyncio
    async def test_rrf_returns_hybrid_mode(self, svc):
        """When only FTS available (no vec), mode should be 'fts'."""
        await svc.remember("authentication module", importance=1)
        result = await svc.recall("authentication", mode="hybrid")
        # With embedding disabled, hybrid falls back to fts
        assert result["mode"] == "fts"
        assert result["count"] > 0

    def test_rrf_score_calculation(self, storage):
        """Verify RRF score formula: 1/(60+rank)."""
        from evermind_mcp.memory_service_v2 import _rrf_score, RRF_K

        # Rank 0 in both: 1/(60+0) + 1/(60+0) = 2/60 = 0.0333...
        score_0_0 = _rrf_score(0, 0)
        expected_0_0 = 2.0 / (RRF_K)
        assert abs(score_0_0 - expected_0_0) < 0.0001

        # Rank 0 and 1: 1/(60+0) + 1/(60+1) = 1/60 + 1/61
        score_0_1 = _rrf_score(0, 1)
        expected_0_1 = 1.0 / RRF_K + 1.0 / (RRF_K + 1)
        assert abs(score_0_1 - expected_0_1) < 0.0001

    @pytest.mark.asyncio
    async def test_rrf_deduplicates(self, tmp_path):
        """Same memory in both FTS and vec results should appear once in output.

        This test requires embedding enabled, so we skip if unavailable.
        """
        cfg = EverMindConfig(
            home=tmp_path, default_space="coding:test", embed_enabled=True
        )
        svc = MemoryService(cfg)

        if not svc.embedder.available:
            pytest.skip("Embedding not available, cannot test hybrid dedup")

        # Store and wait for embedding to complete
        await svc.remember("authentication module implementation", importance=1)
        await asyncio.sleep(0.5)  # Give embedding worker time to process

        result = await svc.recall("authentication module", mode="hybrid", limit=10)

        # Check for duplicate IDs
        ids = [m["id"] for m in result["results"]]
        assert len(ids) == len(set(ids)), "Duplicate memory IDs in hybrid results"


# ============================================================================
# TestGraphLayer - Entity extraction and graph relationships
# ============================================================================


class TestGraphLayer:
    """Test graph entity extraction and linking."""

    def test_entity_extraction_filepath(self, storage):
        """Content with file paths should extract them as entities."""
        content = "The auth.py module handles authentication"
        entities = storage.extract_entities_from_content(content)
        assert "auth.py" in entities

    def test_entity_extraction_camelcase(self, storage):
        """CamelCase identifiers should be extracted."""
        content = "UserService and AuthController handle requests"
        entities = storage.extract_entities_from_content(content)
        assert "UserService" in entities
        assert "AuthController" in entities

    def test_entity_extraction_limit(self, storage):
        """Entity extraction should return a bounded entity set."""
        content = " ".join([f"Entity{i}.py" for i in range(25)])
        entities = storage.extract_entities_from_content(content)
        assert len(entities) <= 30

    def test_upsert_graph_node_idempotent(self, storage):
        """Upserting same node twice should return same ID."""
        id1 = storage.upsert_graph_node("coding:test", "entity", "auth.py")
        id2 = storage.upsert_graph_node("coding:test", "entity", "auth.py")
        assert id1 == id2

    @pytest.mark.asyncio
    async def test_graph_link_and_search(self, svc):
        """Stored memory with entities should be findable via graph_explore."""
        await svc.remember("The auth.py module uses JWT tokens", importance=1)

        result = await svc.graph_explore("auth.py")
        assert result["count"] > 0
        assert any("auth.py" in str(item) for item in result["related_memories"])

    @pytest.mark.asyncio
    async def test_graph_explore_no_results(self, svc):
        """Graph explore for nonexistent entity should return empty."""
        result = await svc.graph_explore("nonexistent.py")
        assert result["count"] == 0
        assert result["related_memories"] == []


# ============================================================================
# TestBriefingConfig - Configurable briefing limits
# ============================================================================


class TestBriefingConfig:
    """Test briefing recent/important count configuration."""

    @pytest.mark.asyncio
    async def test_configurable_recent_count(self, tmp_path):
        """Briefing with recent_limit=3 should return only 3 recent memories."""
        cfg = EverMindConfig(
            home=tmp_path,
            default_space="coding:test",
            embed_enabled=False,
            briefing_recent=3,
        )
        svc = MemoryService(cfg)

        # Store 10 memories
        for i in range(10):
            await svc.remember(f"Memory {i}", importance=0)
            await asyncio.sleep(0.01)  # Ensure different timestamps

        briefing = await svc.briefing()
        assert len(briefing["recent"]) <= 3

    @pytest.mark.asyncio
    async def test_configurable_important_count(self, tmp_path):
        """Briefing with important_limit=2 should return only 2 important memories."""
        cfg = EverMindConfig(
            home=tmp_path,
            default_space="coding:test",
            embed_enabled=False,
            briefing_important=2,
        )
        svc = MemoryService(cfg)

        # Store 5 important memories
        for i in range(5):
            await svc.remember(f"Important memory {i}", importance=1)

        briefing = await svc.briefing()
        assert len(briefing["important"]) <= 2


# ============================================================================
# TestListMemories - List operation filters
# ============================================================================


class TestListMemories:
    """Test memory listing with various filters."""

    @pytest.mark.asyncio
    async def test_list_all(self, svc):
        """List without filters should return all memories."""
        for i in range(5):
            await svc.remember(f"Memory {i}", importance=1)

        result = await svc.list_memories(limit=50)
        assert result["count"] == 5

    @pytest.mark.asyncio
    async def test_list_by_layer(self, svc):
        """List with layer filter should return only that layer."""
        await svc.remember("Working memory", importance=0)  # working layer
        await svc.remember("Archive memory", importance=2)  # archive layer

        result = await svc.list_memories(layer="archive", limit=50)
        assert all(m["layer"] == "archive" for m in result["memories"])

    @pytest.mark.asyncio
    async def test_list_by_tags(self, svc):
        """List with tags filter should return only tagged memories."""
        await svc.remember("Auth memory", importance=1, tags=["auth"])
        await svc.remember("DB memory", importance=1, tags=["database"])

        result = await svc.list_memories(tags=["auth"], limit=50)
        assert all("auth" in m["tags"] for m in result["memories"])

    @pytest.mark.asyncio
    async def test_list_limit(self, svc):
        """List with limit=3 should return at most 3 memories."""
        for i in range(10):
            await svc.remember(f"Memory {i}", importance=1)

        result = await svc.list_memories(limit=3)
        assert len(result["memories"]) <= 3


# ============================================================================
# TestEmbeddingDimProtection - Embedding dimension mismatch handling
# ============================================================================


class TestEmbeddingDimProtection:
    """Test embedding dimension storage and mismatch detection."""

    def test_dim_stored_on_first_use(self, storage):
        """After check_embed_dim(512), get_meta should return '512'."""
        result = storage.check_embed_dim(512)
        assert result is True
        stored = storage.get_meta("embed_dim")
        assert stored == "512"

    def test_dim_match_returns_true(self, storage):
        """Checking same dimension twice should return True both times."""
        result1 = storage.check_embed_dim(512)
        result2 = storage.check_embed_dim(512)
        assert result1 is True
        assert result2 is True

    def test_dim_mismatch_returns_false(self, storage):
        """Dimension mismatch should return False on second call."""
        storage.check_embed_dim(512)
        result = storage.check_embed_dim(384)
        assert result is False

    @pytest.mark.asyncio
    async def test_profile_dimensions_do_not_conflict_with_legacy_vec(self, tmp_path):
        """Versioned profiles coexist with the legacy fixed-width vec table."""
        cfg = EverMindConfig(
            home=tmp_path,
            default_space="coding:test",
            embed_enabled=True,
            embed_warmup_on_start=False,
        )

        # Pre-set dimension in storage
        storage = EmbeddedStorage(cfg.db_path(cfg.default_space))
        storage.set_meta("embed_dim", "512")
        storage.close_all()

        svc = MemoryService(cfg)
        try:
            assert svc.embedder.local_profile.dimensions == 384
            assert int(svc.storage.get_meta("embed_dim")) == 512
            assert svc.embedder._enabled is True
        finally:
            svc.close()


# ============================================================================
# TestProjectDetector - Utility function tests
# ============================================================================


class TestProjectDetector:
    """Test project space detection from git URLs."""

    def test_slug_from_url_ssh(self):
        """SSH git URL should extract repo name."""
        url = "git@github.com:user/my-app.git"
        slug = _slug_from_url(url)
        assert slug == "my-app"

    def test_slug_from_url_https(self):
        """HTTPS git URL should extract repo name."""
        url = "https://github.com/user/my-app.git"
        slug = _slug_from_url(url)
        assert slug == "my-app"

    def test_slug_from_url_no_git_suffix(self):
        """URL without .git suffix should work."""
        url = "https://github.com/user/my-app"
        slug = _slug_from_url(url)
        assert slug == "my-app"


# ============================================================================
# TestStorageMetadata - Meta key-value operations
# ============================================================================


class TestStorageMetadata:
    """Test storage metadata get/set operations."""

    def test_get_nonexistent_meta(self, storage):
        """Getting nonexistent key should return None."""
        value = storage.get_meta("nonexistent_key")
        assert value is None

    def test_set_and_get_meta(self, storage):
        """Set and get should round-trip correctly."""
        storage.set_meta("test_key", "test_value")
        value = storage.get_meta("test_key")
        assert value == "test_value"

    def test_replace_meta(self, storage):
        """Setting same key twice should update value."""
        storage.set_meta("key", "value1")
        storage.set_meta("key", "value2")
        value = storage.get_meta("key")
        assert value == "value2"


# ============================================================================
# TestMemoryExpiry - Working memory expiration
# ============================================================================


class TestMemoryExpiry:
    """Test working memory expiration logic."""

    def test_working_memory_expires(self, storage):
        """Working layer memories should have expires_at set."""
        mem = storage.insert_memory(
            space="coding:test", content="Temporary working memory", layer="working"
        )
        assert mem.expires_at is not None
        assert mem.expires_at > storage._now_ms()

    def test_archive_memory_no_expiry(self, storage):
        """Archive layer memories should not expire."""
        mem = storage.insert_memory(
            space="coding:test", content="Permanent archive memory", layer="archive"
        )
        assert mem.expires_at is None

    def test_expire_working_memories_removes_expired(self, storage):
        """Expired working memories should be removed by expire call."""
        # Insert working memory with past expiry
        now = storage._now_ms()
        past_expiry = now - 1000
        storage.insert_memory(
            space="coding:test", content="Expired memory", layer="working"
        )
        # Manually set expiry to past
        storage.conn.execute(
            "UPDATE memories SET expires_at=? WHERE content=?",
            (past_expiry, "Expired memory"),
        )
        storage.conn.commit()

        count = storage.expire_working_memories("coding:test")
        assert count == 1

        # Verify memory is gone
        results = storage.search_fts("Expired memory", "coding:test")
        assert len(results) == 0


# ============================================================================
# TestMemoryStats - Statistics aggregation
# ============================================================================


class TestMemoryStats:
    """Test memory statistics collection."""

    @pytest.mark.asyncio
    async def test_stats_includes_counts(self, svc):
        """Status should include memory counts."""
        await svc.remember("Memory 1", importance=1)
        await svc.remember("Memory 2", importance=2)

        status = await svc.status()
        assert "total_count" in status
        assert status["total_count"] >= 2

    @pytest.mark.asyncio
    async def test_stats_by_layer(self, svc):
        """Status should break down counts by layer."""
        await svc.remember("Working", importance=0)
        await svc.remember("Archive", importance=2)

        status = await svc.status()
        assert "by_layer" in status
        assert isinstance(status["by_layer"], dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
