from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evermind_mcp.config_v2 import EverMindConfig
import evermind_mcp.archive_bridge as archive_bridge
import evermind_mcp.codebase_engine as codebase_engine
import evermind_mcp.tool_bridge as tool_bridge
from evermind_mcp.archive_bridge import ArchiveBridge
from evermind_mcp.archive_bridge import _archive_args
from evermind_mcp.codebase_engine import CodebaseEngine
from evermind_mcp.memory_service_v2 import MemoryService


def _parse(text_contents) -> dict:
    return json.loads(text_contents[0].text)


def test_unified_tool_surface_contains_memory_codebase_and_archive():
    import evermind_mcp.server_v2 as server_mod

    names = {tool.name for tool in server_mod.TOOLS}
    assert len(names) == 42
    assert {"remember", "update_memory", "recall", "graph_explore"} <= names
    assert {"index_repository", "search_code", "get_architecture"} <= names
    assert {"search_notes", "read_note", "propose_basic_memory_update"} <= names


@pytest.mark.asyncio
async def test_server_dispatches_codebase_and_archive_tools(tmp_path, monkeypatch):
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
    monkeypatch.setattr(
        svc.codebase,
        "call",
        lambda name, args: {"ok": True, "engine": "codebase-memory-mcp", "tool": name, "args": args},
    )
    monkeypatch.setattr(
        svc.archive,
        "call",
        lambda name, args: {"ok": True, "engine": "basic-memory", "tool": name, "args": args},
    )

    codebase = _parse(
        await server_mod.call_tool(
            "search_code",
            {"project": "D-Project-EverMind", "pattern": "server_v2"},
        )
    )
    archive = _parse(await server_mod.call_tool("search_notes", {"query": "EverMind"}))

    assert codebase["engine"] == "codebase-memory-mcp"
    assert codebase["tool"] == "search_code"
    assert archive["engine"] == "basic-memory"
    assert archive["tool"] == "search_notes"
    server_mod._svc = None


@pytest.mark.asyncio
async def test_server_missing_required_argument_returns_clean_error(tmp_path, monkeypatch, caplog):
    import evermind_mcp.server_v2 as server_mod

    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
    )
    svc = MemoryService(cfg)
    server_mod._svc = svc
    monkeypatch.setattr(server_mod, "_maybe_update_space_from_roots", lambda: asyncio.sleep(0))

    with caplog.at_level("ERROR", logger="evermind_mcp.server_v2"):
        result = _parse(await server_mod.call_tool("recall", {}))

    assert result["ok"] is False
    assert result["code"] == "MCP_INVALID_ARGUMENT"
    assert result["message"] == "missing required argument: query"
    assert "Tool recall failed" not in caplog.text
    server_mod._svc = None


@pytest.mark.asyncio
async def test_codebase_verified_negative_memory_beats_unverified_auth_hallucination(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
    )
    svc = MemoryService(cfg)
    await svc.remember("DEEP-TEST: auth.ts manages login token in UserService", importance=1)
    await svc.remember(
        "[PIPELINE] Pinia stores include app.ts, dict.ts, messageCenter.ts; auth.ts does not exist",
        importance=1,
        tags=["codebase-verified"],
        meta={"source": "codebase", "verified_at": "2026-07-09T00:00:00Z"},
    )

    result = await svc.recall("Pinia store 登录态 auth Token", mode="fts", limit=5)
    graph = await svc.graph_explore("auth.ts")

    assert result["results"][0]["verified"] is True
    assert "does not exist" in result["results"][0]["content"]
    assert result["conflicts"]
    assert result["forget_suggestions"][0]["id"]
    assert graph["conflicts"]
    assert graph["forget_suggestions"][0]["id"]


@pytest.mark.asyncio
async def test_update_memory_corrects_content_indexes_graph_and_metadata(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
    )
    svc = MemoryService(cfg)
    created = await svc.remember(
        "DEEP-TEST: auth.ts manages login token in UserService",
        importance=1,
        tags=["unverified"],
    )

    updated = await svc.update_memory(
        created["id"],
        content="[PIPELINE] Pinia stores include app.ts, dict.ts, messageCenter.ts; auth.ts does not exist",
        importance=2,
        tags=["codebase-verified"],
        memory_type="auto",
        meta={"source": "codebase", "verified_at": "2026-07-09T00:00:00Z"},
    )
    old_recall = await svc.recall("UserService login token", mode="fts", limit=5, min_score=0)
    new_recall = await svc.recall("auth.ts does not exist", mode="fts", limit=5, min_score=0)
    old_graph = await svc.graph_explore("UserService")
    new_graph = await svc.graph_explore("auth.ts")

    assert updated["updated"] is True
    assert updated["layer"] == "archive"
    assert updated["type"] == "semantic"
    assert updated["tags"] == ["codebase-verified"]
    assert updated["meta"]["source"] == "codebase"
    assert all(item["id"] != created["id"] for item in old_recall["results"])
    assert new_recall["results"][0]["id"] == created["id"]
    assert old_graph["count"] == 0
    assert new_graph["related_memories"][0]["memory"]["id"] == created["id"]


@pytest.mark.asyncio
async def test_server_dispatches_update_memory(tmp_path, monkeypatch):
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

    remembered = _parse(await server_mod.call_tool("remember", {"content": "wrong module auth.ts"}))
    updated = _parse(
        await server_mod.call_tool(
            "update_memory",
            {
                "id": remembered["id"],
                "content": "correct module ipcManager.ts",
                "tags": ["codebase-verified"],
                "meta": {"source": "codebase"},
            },
        )
    )

    assert updated["updated"] is True
    assert updated["id"] == remembered["id"]
    assert updated["tags"] == ["codebase-verified"]
    server_mod._svc = None


def test_codebase_bridge_detect_changes_normalizes_repo_path_to_project(tmp_path, monkeypatch):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        codebase_memory_path="codebase-memory-mcp",
    )
    engine = CodebaseEngine(cfg)
    calls = []

    monkeypatch.setattr(
        codebase_engine,
        "resolve_executable",
        lambda configured, fallback: "codebase-memory-mcp",
    )

    repo_path = tmp_path / "sample-repo"

    def fake_run_json_command(command, timeout_seconds):
        calls.append((command, timeout_seconds))

        class Result:
            ok = True
            data = (
                {
                    "projects": [
                        {
                            "name": "D-Project-SampleRepo",
                            "root_path": str(repo_path),
                        }
                    ]
                }
                if command[2] == "list_projects"
                else {"ok": True}
            )

            def to_dict(self):
                return {"ok": True, "data": self.data, "latency_ms": 1}

        return Result()

    monkeypatch.setattr(codebase_engine, "run_json_command", fake_run_json_command)

    engine.call("detect_changes", {"repo_path": str(repo_path)})

    list_command, _ = calls[0]
    command, _ = calls[1]
    assert list_command[:3] == ["codebase-memory-mcp", "cli", "list_projects"]
    assert command[:3] == ["codebase-memory-mcp", "cli", "detect_changes"]
    payload = json.loads(command[3])
    assert payload["repo_path"].endswith("sample-repo")
    assert payload["project"] == "D-Project-SampleRepo"


def test_codebase_native_fallback_works_without_external_executable(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text(
        "def alpha():\n"
        "    return beta()\n\n"
        "def beta():\n"
        "    return 'needle'\n",
        encoding="utf-8",
    )
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        codebase_memory_path=str(tmp_path / "missing-codebase-memory-mcp.exe"),
    )
    engine = CodebaseEngine(cfg)

    with patch.dict(os.environ, {"PATH": ""}, clear=False):
        indexed = engine.call("index_repository", {"repo_path": str(repo)})
        project = indexed["project"]
        projects = engine.call("list_projects", {})
        search = engine.call("search_code", {"project": project, "pattern": "needle"})
        graph = engine.call("search_graph", {"project": project, "query": "alpha"})
        snippet = engine.call(
            "get_code_snippet",
            {"project": project, "qualified_name": graph["results"][0]["qualified_name"]},
        )
        architecture = engine.call("get_architecture", {"project": project})
        changes = engine.call("detect_changes", {"repo_path": str(repo)})

    assert indexed["ok"] is True
    assert indexed["fallback"] == "native"
    assert projects["projects"][0]["name"] == project
    assert search["total_results"] == 1
    assert graph["total"] >= 1
    assert "def alpha" in snippet["source"]
    assert architecture["total_files"] == 1
    assert changes["changed_files"] == []


def test_codebase_native_fallback_covers_unified_tool_surface_without_external_executable(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("class Worker:\n    def run(self):\n        return 'ok'\n", encoding="utf-8")
    trace_file = repo / "trace.json"
    trace_file.write_text("[]", encoding="utf-8")
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        codebase_memory_path=str(tmp_path / "missing-codebase-memory-mcp.exe"),
    )
    engine = CodebaseEngine(cfg)

    with patch.dict(os.environ, {"PATH": ""}, clear=False):
        indexed = engine.call("index_repository", {"repo_path": str(repo)})
        project = indexed["project"]
        calls = {
            "list_projects": engine.call("list_projects", {}),
            "index_status": engine.call("index_status", {"project": project}),
            "search_graph": engine.call("search_graph", {"project": project, "query": "Worker"}),
            "trace_path": engine.call("trace_path", {"project": project, "function_name": "run"}),
            "detect_changes": engine.call("detect_changes", {"repo_path": str(repo)}),
            "query_graph": engine.call("query_graph", {"project": project, "query": "MATCH (n) RETURN n LIMIT 3"}),
            "get_graph_schema": engine.call("get_graph_schema", {"project": project}),
            "get_architecture": engine.call("get_architecture", {"project": project}),
            "search_code": engine.call("search_code", {"project": project, "pattern": "Worker"}),
            "manage_adr": engine.call("manage_adr", {"project": project, "mode": "list"}),
            "ingest_traces": engine.call("ingest_traces", {"project": project, "trace_path": str(trace_file)}),
        }
        snippet = engine.call(
            "get_code_snippet",
            {
                "project": project,
                "qualified_name": calls["search_graph"]["results"][0]["qualified_name"],
                "include_neighbors": True,
            },
        )
        deleted = engine.call("delete_project", {"project": project})

    assert indexed["ok"] is True
    assert all(result["ok"] for result in calls.values())
    assert snippet["ok"] is True
    assert deleted["deleted"] is True
    assert all(result["fallback"] == "native" for result in [indexed, *calls.values(), snippet, deleted])


def test_codebase_native_fallback_detect_changes_resolves_project_from_repo_path(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def alpha():\n    return 'ok'\n", encoding="utf-8")
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        codebase_memory_path=str(tmp_path / "missing-codebase-memory-mcp.exe"),
    )
    engine = CodebaseEngine(cfg)

    with patch.dict(os.environ, {"PATH": ""}, clear=False):
        indexed = engine.call("index_repository", {"repo_path": str(repo), "project": "explicit-project"})
        changes = engine.call("detect_changes", {"repo_path": str(repo)})

    assert indexed["project"] == "explicit-project"
    assert changes["ok"] is True
    assert changes["changed_files"] == []


def test_archive_bridge_list_workspaces_local_does_not_require_cloud(tmp_path, monkeypatch):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
        basic_memory_path="basic-memory",
    )
    bridge = ArchiveBridge(cfg)

    monkeypatch.setattr(
        archive_bridge,
        "resolve_executable",
        lambda configured, fallback: "basic-memory",
    )
    monkeypatch.setattr(
        archive_bridge,
        "run_json_command",
        lambda *args, **kwargs: pytest.fail("local list_workspaces should not call CLI"),
    )

    result = bridge.call("list_workspaces", {"local": True})

    assert result["ok"] is True
    assert result["workspaces"] == []
    assert result["cloud_available"] is False
    assert result["reason"] == "local_mode_no_cloud"


def test_archive_fast_path_reads_writes_and_searches_without_cli(tmp_path, monkeypatch):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)
    monkeypatch.setattr(
        archive_bridge,
        "run_json_command",
        lambda *args, **kwargs: pytest.fail("local fast path should not call CLI"),
    )

    written = bridge.call(
        "write_note",
        {
            "title": "Eval Note",
            "folder": "eval",
            "content": "Initial content",
            "project": "sample",
            "local": True,
            "overwrite": True,
            "tags": ["eval"],
        },
    )
    read = bridge.call("read_note", {"identifier": "eval/eval-note", "project": "sample"})
    search = bridge.call("search_notes", {"query": "Initial", "project": "sample"})
    projects = bridge.call("list_memory_projects", {"local": True})

    assert written["ok"] is True
    assert written["fast_path"] is True
    assert read["content"].startswith("# Eval Note")
    assert search["count"] == 1
    assert projects["projects"][0]["name"] == "sample"


def test_archive_fast_path_search_identifier_can_be_read_without_project(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)
    bridge.call(
        "write_note",
        {
            "title": "Cross Project Note",
            "folder": "eval",
            "content": "needle",
            "project": "sample",
            "overwrite": True,
        },
    )

    search = bridge.call("search_notes", {"query": "needle"})
    read = bridge.call("read_note", {"identifier": search["results"][0]["identifier"]})

    assert search["results"][0]["identifier"] == "sample/eval/cross-project-note"
    assert read["ok"] is True
    assert "needle" in read["content"]


def test_archive_fast_path_project_slug_cannot_escape_archive_root(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)

    result = bridge.call(
        "write_note",
        {
            "title": "Safe Note",
            "folder": "eval",
            "content": "safe",
            "project": "..",
            "overwrite": True,
        },
    )

    assert result["ok"] is True
    assert (tmp_path / "archive" / "projects" / "default" / "eval" / "safe-note.md").exists()
    assert not (tmp_path / "archive" / "eval" / "safe-note.md").exists()


def test_archive_fast_path_concurrent_append_is_recoverable(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)
    bridge.call(
        "write_note",
        {
            "title": "Concurrent Note",
            "folder": "eval",
            "content": "base",
            "project": "sample",
            "overwrite": True,
        },
    )

    def append_line(index: int) -> dict:
        return bridge.call(
            "edit_note",
            {
                "identifier": "eval/concurrent-note",
                "operation": "append",
                "content": f"line-{index}",
                "project": "sample",
            },
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(append_line, range(16)))

    read = bridge.call("read_note", {"identifier": "eval/concurrent-note", "project": "sample"})

    assert all(item["ok"] for item in results)
    for index in range(16):
        assert f"line-{index}" in read["content"]


def test_archive_fast_path_recovers_from_stale_tmp_and_lock(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)
    first = bridge.call(
        "write_note",
        {
            "title": "Crash Note",
            "folder": "eval",
            "content": "stable content",
            "project": "sample",
            "overwrite": True,
        },
    )
    note_path = tmp_path / "archive" / "projects" / "sample" / "eval" / "crash-note.md"
    stale_time = time.time() - 120
    (note_path.parent / "crash-note.md.leftover.tmp").write_text("partial", encoding="utf-8")
    lock_path = note_path.with_name(note_path.name + ".lock")
    lock_path.write_text("stale", encoding="utf-8")
    os.utime(lock_path, (stale_time, stale_time))

    second = bridge.call(
        "edit_note",
        {
            "identifier": "eval/crash-note",
            "operation": "append",
            "content": "after restart",
            "project": "sample",
        },
    )
    read = bridge.call("read_note", {"identifier": "eval/crash-note", "project": "sample"})

    assert first["ok"] is True
    assert second["ok"] is True
    assert "stable content" in read["content"]
    assert "after restart" in read["content"]
    assert not lock_path.exists()


def test_archive_fast_path_error_schema_is_machine_readable(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)

    result = bridge.call("write_note", {"folder": "missing-title"})

    assert result["ok"] is False
    assert result["code"] == "ARCHIVE_INVALID_ARGUMENT"
    assert result["message"]
    assert result["retryable"] is False


def test_run_json_command_sanitizes_python_env(monkeypatch):
    captured = {}
    monkeypatch.setenv("PYTHONHOME", "bad-home")
    monkeypatch.setenv("PYTHONPATH", "bad-path")
    monkeypatch.setenv("PYTHONNOUSERSITE", "1")

    def fake_run(command, **kwargs):
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr(tool_bridge.subprocess, "run", fake_run)

    result = tool_bridge.run_json_command(["basic-memory", "tool", "list-projects"], timeout_seconds=1)

    assert result.ok is True
    assert "PYTHONHOME" not in captured["env"]
    assert "PYTHONPATH" not in captured["env"]
    assert "PYTHONNOUSERSITE" not in captured["env"]


def test_archive_bridge_maps_write_note_arguments_to_basic_memory_cli():
    command = _archive_args(
        "write_note",
        {
            "title": "Project Overview",
            "folder": "evermind",
            "content": "Body",
            "tags": ["evermind", "mcp"],
            "type": ["note"],
            "project": "default",
            "overwrite": True,
            "local": True,
        },
    )

    assert command[:4] == ["--title", "Project Overview", "--folder", "evermind"]
    assert ["--content", "Body"] == command[4:6]
    assert "--tags" in command
    assert command[command.index("--tags") + 1] == "evermind,mcp"
    assert "--project" in command
    assert command[command.index("--project") + 1] == "default"
    assert "--overwrite" in command
    assert "--local" in command
