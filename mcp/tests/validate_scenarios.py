"""
EverMind v2 — Complete scenario validation.

Run with: uv run --directory . python tests/validate_scenarios.py
"""

import asyncio
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, "src")

from evermind_mcp.config_v2 import EverMindConfig
from evermind_mcp.memory_service_v2 import MemoryService
from evermind_mcp.project_detector import _slug_from_url

PASSED = []
FAILED = []


def ok(label: str) -> None:
    PASSED.append(label)
    print(f"  [PASS] {label}")


def fail_case(label: str, detail: str) -> None:
    FAILED.append(f"{label}: {detail}")
    print(f"  [FAIL] {label}: {detail}")


def make_svc(tmp: str, space: str = "coding:myapp") -> MemoryService:
    cfg = EverMindConfig(
        home=pathlib.Path(tmp),
        default_space=space,
        embed_enabled=False,
    )
    return MemoryService(cfg)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 1: New project — briefing returns empty, agent knows to explore
# ─────────────────────────────────────────────────────────────────────────────
def test_new_project_briefing():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            briefing = asyncio.run(service.briefing())
            assert "memory_count" in briefing
            assert briefing["memory_count"] == 0
            assert "space" in briefing
            assert "recent" in briefing and isinstance(briefing["recent"], list)
            assert "important" in briefing and isinstance(briefing["important"], list)
        finally:
            time.sleep(0.05)
            service.storage.close_all()
    ok("Scenario 1 — new project: briefing returns memory_count=0, triggers codebase exploration")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 2: Seeded memories survive session restart
# ─────────────────────────────────────────────────────────────────────────────
def test_seed_and_persist():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            asyncio.run(service.remember("Tech stack: Python 3.12, FastAPI, PostgreSQL", importance=1))
            asyncio.run(service.remember("Entry point: main.py — run with: uvicorn main:app", importance=1))
            asyncio.run(service.remember("Build: make build  Test: pytest -q", importance=1))
            briefing = asyncio.run(service.briefing())
            assert briefing["memory_count"] == 3
        finally:
            time.sleep(0.05)
            service.storage.close_all()

        # New session — recreate service pointing at same DB
        service2 = make_svc(tmp)
        try:
            briefing2 = asyncio.run(service2.briefing())
            assert briefing2["memory_count"] == 3, "memories must survive session restart"
            assert len(briefing2["recent"]) == 3
        finally:
            time.sleep(0.05)
            service2.storage.close_all()
    ok("Scenario 2 — seeded memories persist across sessions (new MemoryService instance)")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 3: Returning user — recall finds stored memories
# ─────────────────────────────────────────────────────────────────────────────
def test_returning_user_recall():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            asyncio.run(service.remember("Authentication uses JWT with 15 min expiry", importance=1))
            asyncio.run(service.remember("Known bug: token refresh fails on mobile", importance=1))
            asyncio.run(service.remember("Deploy: kubectl apply -f k8s/", importance=2))

            r = asyncio.run(service.recall("authentication JWT"))
            assert r["count"] > 0
            assert any("JWT" in m["content"] for m in r["results"])

            r2 = asyncio.run(service.recall("deploy kubectl"))
            assert r2["count"] > 0
        finally:
            time.sleep(0.05)
            service.storage.close_all()
    ok("Scenario 3 — returning user: recall() surfaces relevant memories correctly")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 4: Layer assignment by importance
# ─────────────────────────────────────────────────────────────────────────────
def test_layer_assignment():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            r0 = asyncio.run(service.remember("temporary scratch note", importance=0))
            r1 = asyncio.run(service.remember("important auth module fact", importance=1))
            r2 = asyncio.run(service.remember("decided to use PostgreSQL for JSONB", importance=2))

            assert r0["layer"] == "working", f"got {r0['layer']}"
            assert r2["layer"] == "archive", f"got {r2['layer']}"
            assert r1["layer"] in ("episodic", "semantic", "procedural"), f"got {r1['layer']}"
        finally:
            time.sleep(0.05)
            service.storage.close_all()
    ok("Scenario 4 — layer assignment: working/long-term/archive by importance value")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 5: Auto memory type detection from content
# ─────────────────────────────────────────────────────────────────────────────
def test_auto_type_detection():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            r_bug  = asyncio.run(service.remember("fixed the null pointer exception in auth.py line 42"))
            r_dec  = asyncio.run(service.remember("decided to use Redis for session storage"))
            r_proc = asyncio.run(service.remember("deploy steps: 1. build 2. push 3. kubectl apply"))
            r_pref = asyncio.run(service.remember("prefer async handlers over sync for all endpoints"))

            assert r_bug["type"]  == "bug",        f"got {r_bug['type']}"
            assert r_dec["type"]  == "decision",   f"got {r_dec['type']}"
            assert r_proc["type"] == "procedural", f"got {r_proc['type']}"
            assert r_pref["type"] == "preference", f"got {r_pref['type']}"
        finally:
            time.sleep(0.05)
            service.storage.close_all()
    ok("Scenario 5 — auto type detection: bug/decision/procedural/preference all correct")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 6: Duplicate content is merged, not stored twice
# ─────────────────────────────────────────────────────────────────────────────
def test_dedup():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            asyncio.run(service.remember("The database is PostgreSQL 15"))
            r2 = asyncio.run(service.remember("The database is PostgreSQL 15"))
            stats = asyncio.run(service.status())
            assert stats["total_count"] == 1, f"dedup failed, got {stats['total_count']}"
            assert r2["action"] == "merged", f"got {r2['action']}"
        finally:
            time.sleep(0.05)
            service.storage.close_all()
    ok("Scenario 6 — dedup: identical content merged, not stored twice")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 7: Working memory auto-expires
# ─────────────────────────────────────────────────────────────────────────────
def test_working_memory_expires():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            now_ms = int(time.time() * 1000)
            conn = service.storage.conn
            conn.execute(
                "INSERT INTO memories(id,content,space,layer,memory_type,role,"
                "importance,tags,meta,created_at,updated_at,expires_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ("exp-001", "stale temp note", "coding:myapp", "working",
                 "episodic", "user", 0, "[]", "{}", now_ms - 100000,
                 now_ms - 100000, now_ms - 1000),
            )
            conn.commit()

            asyncio.run(service.recall("anything"))

            row = conn.execute("SELECT id FROM memories WHERE id='exp-001'").fetchone()
            assert row is None, "expired working memory must be deleted"
        finally:
            time.sleep(0.05)
            service.storage.close_all()
    ok("Scenario 7 — working memory auto-expiry: stale entries deleted on recall()")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 8: forget() fully removes a memory
# ─────────────────────────────────────────────────────────────────────────────
def test_forget():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            r = asyncio.run(service.remember("memory to delete"))
            memory_id = r["id"]
            del_result = asyncio.run(service.forget(memory_id))
            assert del_result["deleted"] is True
            check = asyncio.run(service.recall("memory to delete"))
            assert check["count"] == 0
        finally:
            time.sleep(0.05)
            service.storage.close_all()
    ok("Scenario 8 — forget(): memory fully removed from storage and search index")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 9: Project space auto-detection from git remote
# ─────────────────────────────────────────────────────────────────────────────
def test_project_detection():
    cases = [
        ("git@github.com:user/my-awesome-project.git", "my-awesome-project"),
        ("https://github.com/org/EverMind.git",         "evermind"),
        ("https://github.com/org/My_Project.git",       "my-project"),
        ("https://github.com/org/some-repo",            "some-repo"),
        ("git@gitlab.com:team/api-service.git",         "api-service"),
    ]
    for url, expected in cases:
        got = _slug_from_url(url)
        assert got == expected, f"URL {url!r}: expected {expected!r}, got {got!r}"
    ok("Scenario 9 — project detection: git remote URLs correctly slugified")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 10: Offline / no-embedding mode — FTS fallback, no errors
# ─────────────────────────────────────────────────────────────────────────────
def test_offline_mode():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            asyncio.run(service.remember("works without embedding model"))
            r = asyncio.run(service.recall("embedding"))
            assert r["mode"] in ("fts", "hybrid")
            status = asyncio.run(service.status())
            assert status["embedding_available"] is False
        finally:
            time.sleep(0.05)
            service.storage.close_all()
    ok("Scenario 10 — offline mode: FTS fallback works, no embedding required")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 11: MCP tool schema completeness
# ─────────────────────────────────────────────────────────────────────────────
def test_mcp_tools():
    import importlib
    server_mod = importlib.import_module("evermind_mcp.server_v2")
    tool_names = {t.name for t in server_mod.TOOLS}
    required = {
        "remember",
        "update_memory",
        "recall",
        "forget",
        "briefing",
        "list",
        "graph_explore",
        "status",
        "export",
        "compact",
        "tags",
        "reindex",
        "health",
        "list_spaces",
        "index_repository",
        "search_code",
        "search_graph",
        "trace_path",
        "get_architecture",
        "search_notes",
        "read_note",
        "write_note",
        "propose_basic_memory_update",
        "commit_basic_memory_update",
    }
    missing = required - tool_names
    assert not missing, f"Missing MCP tools: {missing}"
    assert len(tool_names) == 42, f"Expected 42 unified MCP tools, got {len(tool_names)}"
    for tool in server_mod.TOOLS:
        assert tool.description, f"Tool {tool.name} missing description"
        assert tool.inputSchema,  f"Tool {tool.name} missing inputSchema"
    recall_schema = next(t.inputSchema for t in server_mod.TOOLS if t.name == "recall")
    briefing_schema = next(t.inputSchema for t in server_mod.TOOLS if t.name == "briefing")
    update_schema = next(t.inputSchema for t in server_mod.TOOLS if t.name == "update_memory")
    assert "min_score" in recall_schema["properties"], "recall must expose min_score"
    assert "fast" in briefing_schema["properties"], "briefing must expose fast"
    assert "content" in update_schema["properties"], "update_memory must expose content"
    ok("Scenario 11 — MCP tools: all 42 unified tools registered with description and schema")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 12: Graph tables exist (Phase 3 ready)
# ─────────────────────────────────────────────────────────────────────────────
def test_graph_tables():
    with tempfile.TemporaryDirectory() as tmp:
        service = make_svc(tmp)
        try:
            conn = service.storage.conn
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            assert "graph_nodes" in tables, "graph_nodes missing"
            assert "graph_edges" in tables, "graph_edges missing"
            assert "event_log"   in tables, "event_log missing"
        finally:
            time.sleep(0.05)
            service.storage.close_all()
    ok("Scenario 12 — graph tables: nodes/edges/event_log exist, ready for Phase 3")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 13: Single install command installs ALL tools
# ─────────────────────────────────────────────────────────────────────────────
def test_single_install_command():
    # pyproject.toml is one level up from tests/
    mcp_dir    = pathlib.Path(__file__).parent.parent          # mcp/
    pyproject  = mcp_dir / "pyproject.toml"
    scripts_dir = mcp_dir.parent / "scripts"                   # project root / scripts/

    content = pyproject.read_text(encoding="utf-8")
    assert "full" in content,             "pyproject.toml must have 'full' optional-dependency group"
    assert "sqlite-vec" in content,       "sqlite-vec must be listed"
    assert "sentence-transformers" in content, "sentence-transformers must be listed"
    assert "server_v2:main_sync" in content,   "entry point must point to server_v2"

    win_script = (scripts_dir / "setup-windows.ps1").read_text(encoding="utf-8")
    mac_script = (scripts_dir / "setup-macos.sh").read_text(encoding="utf-8")
    win_all_script = (scripts_dir / "windows" / "install-all.ps1").read_text(encoding="utf-8")
    mac_all_script = (scripts_dir / "macos" / "install-all.sh").read_text(encoding="utf-8")
    native_codebase = (mcp_dir / "src" / "evermind_mcp" / "native_codebase.py").read_text(encoding="utf-8")
    codebase_engine = (mcp_dir / "src" / "evermind_mcp" / "codebase_engine.py").read_text(encoding="utf-8")
    assert "--extra full" in win_script, "setup-windows.ps1 must use --extra full"
    assert "--extra full" in mac_script, "setup-macos.sh must use --extra full"
    assert "install-all.ps1" in win_script, "setup-windows.ps1 must install integrated engines"
    assert "install-all.sh" in mac_script, "setup-macos.sh must install integrated engines"
    assert "v0.9.0" in win_all_script, "Windows install-all must install codebase-memory-mcp v0.9.0"
    assert "v0.9.0" in mac_all_script, "macOS install-all must install codebase-memory-mcp v0.9.0"
    assert "class NativeCodebase" in native_codebase, "EverMind must provide native codebase fallback"
    assert "NativeCodebase(self.config).call" in codebase_engine, "CodebaseEngine must fallback when binary is missing"

    ok("Scenario 13 — single install: EverMind installs or natively provides memory, codebase, and archive engines")


# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("=" * 65)
    print("  EverMind v2 — Complete Scenario Validation")
    print("=" * 65)
    print()

    tests = [
        test_new_project_briefing,
        test_seed_and_persist,
        test_returning_user_recall,
        test_layer_assignment,
        test_auto_type_detection,
        test_dedup,
        test_working_memory_expires,
        test_forget,
        test_project_detection,
        test_offline_mode,
        test_mcp_tools,
        test_graph_tables,
        test_single_install_command,
    ]

    for test in tests:
        try:
            test()
        except Exception as exc:
            FAILED.append(f"{test.__name__}: {exc}")
            print(f"  [FAIL] {test.__name__}: {exc}")

    print()
    print("=" * 65)
    total  = len(tests)
    passed = total - len(FAILED)
    print(f"  Result: {passed}/{total} passed")
    if FAILED:
        print()
        print("  FAILURES:")
        for f in FAILED:
            print(f"    {f}")
    print("=" * 65)
    sys.exit(0 if not FAILED else 1)
