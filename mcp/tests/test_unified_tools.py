from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from evermind_mcp.config_v2 import EverMindConfig
import evermind_mcp.archive_bridge as archive_bridge
from evermind_mcp.archive_bridge import ArchiveBridge
from evermind_mcp.codebase_engine import CodebaseEngine
from evermind_mcp.vendored_codebase import EXPECTED_TREE_SITTER_GRAMMAR_COUNT, REQUIRED_HYBRID_LSP_FILES
from evermind_mcp.memory_service_v2 import MemoryService


def _parse(text_contents) -> dict:
    return json.loads(text_contents[0].text)


def _write_minimal_vendored_codebase_source(source: Path) -> None:
    (source / "src" / "mcp").mkdir(parents=True)
    cbm = source / "internal" / "cbm"
    grammars = cbm / "vendored" / "grammars"
    lsp = cbm / "lsp"
    ts_api = cbm / "vendored" / "ts_runtime" / "include" / "tree_sitter"
    grammars.mkdir(parents=True)
    lsp.mkdir(parents=True)
    ts_api.mkdir(parents=True)
    (source / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (source / "THIRD_PARTY.md").write_text("third-party notices\n", encoding="utf-8")
    (source / "README.md").write_text("vendored codebase-memory-mcp\n", encoding="utf-8")
    (source / "Makefile.cbm").write_text("cbm:\n\t@echo ok\n", encoding="utf-8")
    (source / "src" / "mcp" / "mcp.c").write_text("/* fake */\n", encoding="utf-8")
    (cbm / "cbm.c").write_text("/* fake */\n", encoding="utf-8")
    (cbm / "lsp_all.c").write_text("/* fake */\n", encoding="utf-8")
    (grammars / "MANIFEST.md").write_text("Grammars: 159\n", encoding="utf-8")
    (ts_api / "api.h").write_text("/* fake */\n", encoding="utf-8")
    for index in range(EXPECTED_TREE_SITTER_GRAMMAR_COUNT):
        (grammars / f"lang_{index:03d}").mkdir()
    for name in REQUIRED_HYBRID_LSP_FILES:
        (lsp / name).write_text("/* fake */\n", encoding="utf-8")


def _native_only_config(tmp_path: Path) -> EverMindConfig:
    return EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        codebase_source_dir=tmp_path / "missing-codebase-source",
        codebase_binary_path=tmp_path / "missing-codebase-binary",
    )


def test_unified_tool_surface_contains_memory_codebase_and_archive():
    import evermind_mcp.server_v2 as server_mod

    names = {tool.name for tool in server_mod.TOOLS}
    assert len(names) == 42
    assert {"remember", "update_memory", "recall", "graph_explore"} <= names
    assert {"index_repository", "search_code", "get_architecture"} <= names
    assert {"search_notes", "read_note", "propose_basic_memory_update"} <= names


def test_archive_tool_schema_is_local_only():
    import evermind_mcp.server_v2 as server_mod

    archive_tools = {tool.name: tool for tool in server_mod.TOOLS if tool.name in archive_bridge.ARCHIVE_TOOL_NAMES}
    for name, tool in archive_tools.items():
        properties = tool.inputSchema["properties"]
        assert "cloud" not in properties, name
    assert archive_tools["list_workspaces"].description == "List local archive workspaces."


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
        lambda name, args: {"ok": True, "engine": "evermind-code-graph", "tool": name, "args": args},
    )
    monkeypatch.setattr(
        svc.archive,
        "call",
        lambda name, args: {"ok": True, "engine": "evermind-archive", "tool": name, "args": args},
    )

    codebase = _parse(
        await server_mod.call_tool(
            "search_code",
            {"project": "D-Project-EverMind", "pattern": "server_v2"},
        )
    )
    archive = _parse(await server_mod.call_tool("search_notes", {"query": "EverMind"}))

    assert codebase["engine"] == "evermind-code-graph"
    assert codebase["tool"] == "search_code"
    assert archive["engine"] == "evermind-archive"
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
async def test_server_unknown_tool_returns_machine_readable_error(tmp_path, monkeypatch):
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

    result = _parse(await server_mod.call_tool("not_a_tool", {}))

    assert result["ok"] is False
    assert result["code"] == "MCP_UNKNOWN_TOOL"
    assert result["message"] == "unknown MCP tool: not_a_tool"
    assert result["retryable"] is False
    server_mod._svc = None


@pytest.mark.asyncio
async def test_all_42_mcp_tools_execute_through_server_router(tmp_path, monkeypatch):
    import evermind_mcp.server_v2 as server_mod

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "def alpha():\n"
        "    return beta()\n\n"
        "def beta():\n"
        "    return 'needle'\n",
        encoding="utf-8",
    )
    trace_file = repo / "trace.json"
    trace_file.write_text("[]", encoding="utf-8")
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:smoke",
        embed_enabled=False,
        rerank_enabled=False,
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    cfg.home.mkdir(parents=True)
    svc = MemoryService(cfg)
    server_mod._svc = svc
    monkeypatch.setattr(server_mod, "_maybe_update_space_from_roots", lambda: asyncio.sleep(0))

    results: dict[str, dict] = {}

    remembered = _parse(
        await server_mod.call_tool(
            "remember",
            {"content": "42-smoke alpha memory", "importance": 1, "tags": ["smoke"]},
        )
    )
    results["remember"] = remembered
    results["update_memory"] = _parse(
        await server_mod.call_tool(
            "update_memory",
            {
                "id": remembered["id"],
                "content": "42-smoke alpha memory updated",
                "tags": ["smoke", "updated"],
            },
        )
    )
    results["recall"] = _parse(
        await server_mod.call_tool(
            "recall",
            {"query": "alpha memory", "mode": "fts", "min_score": 0},
        )
    )
    forget_memory = _parse(await server_mod.call_tool("remember", {"content": "42-smoke forget me"}))
    results["forget"] = _parse(await server_mod.call_tool("forget", {"id": forget_memory["id"]}))

    for name, args in {
        "briefing": {"fast": True},
        "list": {"limit": 5},
        "graph_explore": {"entity": "alpha"},
        "status": {},
        "export": {"format": "json"},
        "compact": {"older_than_days": 1},
        "tags": {},
        "reindex": {},
        "health": {},
        "list_spaces": {},
    }.items():
        results[name] = _parse(await server_mod.call_tool(name, args))

    indexed = _parse(
        await server_mod.call_tool(
            "index_repository",
            {"repo_path": str(repo), "project": "smoke-project"},
        )
    )
    results["index_repository"] = indexed
    project = indexed["project"]
    graph = _parse(await server_mod.call_tool("search_graph", {"project": project, "query": "alpha"}))
    results["search_graph"] = graph
    qualified_name = graph["results"][0]["qualified_name"]

    for name, args in {
        "list_projects": {},
        "index_status": {"project": project},
        "search_code": {"project": project, "pattern": "needle"},
        "trace_path": {"project": project, "function_name": "alpha", "depth": 2},
        "detect_changes": {"project": project},
        "query_graph": {"project": project, "query": "MATCH (n) RETURN n LIMIT 2", "limit": 2},
        "get_graph_schema": {"project": project},
        "get_architecture": {"project": project},
        "get_code_snippet": {
            "project": project,
            "qualified_name": qualified_name,
            "include_neighbors": True,
        },
        "manage_adr": {
            "project": project,
            "mode": "update",
            "title": "Smoke ADR",
            "content": "Use local engines",
        },
        "ingest_traces": {"project": project, "trace_path": str(trace_file)},
    }.items():
        results[name] = _parse(await server_mod.call_tool(name, args))
    results["delete_project"] = _parse(await server_mod.call_tool("delete_project", {"project": project}))

    results["write_note"] = _parse(
        await server_mod.call_tool(
            "write_note",
            {
                "title": "Smoke Note",
                "folder": "eval",
                "content": "Smoke content with [[Related Note]]",
                "project": "smoke",
                "overwrite": True,
                "tags": ["smoke"],
                "type": "decision",
            },
        )
    )
    _parse(
        await server_mod.call_tool(
            "write_note",
            {
                "title": "Related Note",
                "folder": "eval",
                "content": "Backlink to [[Smoke Note]]",
                "project": "smoke",
                "overwrite": True,
            },
        )
    )

    for name, args in {
        "read_note": {"identifier": "eval/smoke-note", "project": "smoke"},
        "edit_note": {
            "identifier": "eval/smoke-note",
            "operation": "append",
            "content": "Appended",
            "project": "smoke",
        },
        "build_context": {"url": "memory://eval/smoke-note", "project": "smoke"},
        "recent_activity": {"project": "smoke"},
        "search_notes": {
            "query": "Smoke",
            "project": "smoke",
            "tags": ["smoke"],
            "type": "decision",
        },
        "list_memory_projects": {},
        "list_workspaces": {},
        "schema_validate": {"project": "smoke"},
        "schema_infer": {"note_type": "decision", "project": "smoke"},
        "schema_diff": {"note_type": "decision", "project": "smoke"},
    }.items():
        results[name] = _parse(await server_mod.call_tool(name, args))

    candidate = _parse(
        await server_mod.call_tool(
            "propose_basic_memory_update",
            {
                "project_slug": "smoke",
                "target_file": "测试与验证.md",
                "content": "42 tool smoke passed",
                "evidence": "server_v2.call_tool",
                "reason": "smoke",
            },
        )
    )
    results["propose_basic_memory_update"] = candidate
    results["commit_basic_memory_update"] = _parse(
        await server_mod.call_tool(
            "commit_basic_memory_update",
            {"candidate_id": candidate["candidate_id"], "confirmed": True},
        )
    )
    results["delete_note"] = _parse(
        await server_mod.call_tool(
            "delete_note",
            {"identifier": "eval/smoke-note", "project": "smoke"},
        )
    )

    tool_names = {tool.name for tool in server_mod.TOOLS}
    failures = {name: result for name, result in results.items() if result.get("ok", True) is False}

    assert len(tool_names) == 42
    assert tool_names == set(results)
    assert failures == {}
    assert results["status"]["codebase_source_integrated"] is True
    assert results["status"]["codebase_backend"] in {"native-python", "vendored-codebase-memory-mcp"}
    assert results["status"]["provider_boundary"]["mode"] == "local"
    assert results["status"]["provider_boundary"]["bridge_runtime_allowed"] is False
    assert results["status"]["archive_backend"] == "source-fused-basic-memory"
    assert results["write_note"]["native"] is True
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


def test_codebase_native_engine_works_without_external_executable(tmp_path):
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
    cfg = _native_only_config(tmp_path)
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
    assert indexed["engine"] == "evermind-code-graph"
    assert indexed["native"] is True
    assert indexed["fallback"] == "native"
    assert indexed["edges"] >= 3
    assert projects["projects"][0]["name"] == project
    assert projects["projects"][0]["edges"] == indexed["edges"]
    assert search["total_results"] == 1
    assert graph["total"] >= 1
    assert "def alpha" in snippet["source"]
    assert architecture["total_files"] == 1
    assert architecture["call_edges"] >= 1
    assert changes["changed_files"] == []


def test_codebase_native_engine_covers_unified_tool_surface_without_external_executable(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("class Worker:\n    def run(self):\n        return 'ok'\n", encoding="utf-8")
    trace_file = repo / "trace.json"
    trace_file.write_text("[]", encoding="utf-8")
    cfg = _native_only_config(tmp_path)
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
    assert all(result["engine"] == "evermind-code-graph" for result in [indexed, *calls.values(), snippet, deleted])
    assert all(result["native"] is True for result in [indexed, *calls.values(), snippet, deleted])
    assert all(result["fallback"] == "native" for result in [indexed, *calls.values(), snippet, deleted])
    assert calls["get_graph_schema"]["edge_types"]


def test_codebase_native_engine_builds_python_call_edges_and_impact(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text(
        "def alpha():\n"
        "    return beta()\n\n"
        "def beta():\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )
    cfg = _native_only_config(tmp_path)
    engine = CodebaseEngine(cfg)

    indexed = engine.call("index_repository", {"repo_path": str(repo), "project": "call-edge-demo"})
    trace_alpha = engine.call("trace_path", {"project": "call-edge-demo", "function_name": "alpha"})
    trace_beta = engine.call("trace_path", {"project": "call-edge-demo", "function_name": "beta"})

    source.write_text(
        "def alpha():\n"
        "    return beta()\n\n"
        "def beta():\n"
        "    return 'changed'\n",
        encoding="utf-8",
    )
    changes = engine.call("detect_changes", {"project": "call-edge-demo"})

    assert indexed["edges"] >= 3
    assert any(item["qualified_name"].endswith(".beta") for item in trace_alpha["callees"])
    assert any(item["qualified_name"].endswith(".alpha") for item in trace_beta["callers"])
    impacted = {item["name"] for item in changes["impacted_symbols"]}
    assert {"alpha", "beta"} <= impacted


def test_codebase_engine_prefers_vendored_binary_over_path(tmp_path):
    source = tmp_path / "third_party" / "codebase-memory-mcp"
    _write_minimal_vendored_codebase_source(source)

    if os.name == "nt":
        internal_binary = source / "build" / "c" / "codebase-memory-mcp.cmd"
        internal_binary.parent.mkdir(parents=True)
        internal_binary.write_text(
            '@echo off\r\necho {"ok":true,"tool":"%3","project":"vendored-project","nodes":11,"edges":22}\r\n',
            encoding="utf-8",
        )
    else:
        internal_binary = source / "build" / "c" / "codebase-memory-mcp"
        internal_binary.parent.mkdir(parents=True)
        internal_binary.write_text(
            '#!/usr/bin/env sh\nprintf \'{"ok":true,"tool":"index_repository","project":"vendored-project","nodes":11,"edges":22}\\n\'\n',
            encoding="utf-8",
        )
        internal_binary.chmod(0o755)

    fake_path = tmp_path / "external-bin"
    fake_path.mkdir()
    marker = tmp_path / "external-called.txt"
    (fake_path / "codebase-memory-mcp.cmd").write_text(
        f"@echo off\r\necho external >> \"{marker}\"\r\nexit /b 42\r\n",
        encoding="utf-8",
    )
    (fake_path / "codebase-memory-mcp").write_text(
        f"#!/usr/bin/env sh\necho external >> '{marker.as_posix()}'\nexit 42\n",
        encoding="utf-8",
    )
    (fake_path / "codebase-memory-mcp").chmod(0o755)

    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        codebase_source_dir=source,
        codebase_binary_path=internal_binary,
    )
    engine = CodebaseEngine(cfg)

    with patch.dict(os.environ, {"PATH": str(fake_path)}, clear=False):
        result = engine.call("index_repository", {"repo_path": str(tmp_path)})

    assert result["ok"] is True
    assert result["backend"] == "vendored-codebase-memory-mcp"
    assert result["fallback"] == "vendored"
    assert result["source_integrated"] is True
    assert result["tree_sitter_grammar_count"] == EXPECTED_TREE_SITTER_GRAMMAR_COUNT
    assert result["hybrid_lsp_files_present"] == list(REQUIRED_HYBRID_LSP_FILES)
    assert result["binary_path"] == str(internal_binary)
    assert not marker.exists()


def test_vendored_codebase_uses_piped_json_protocol(tmp_path):
    source = tmp_path / "third_party" / "codebase-memory-mcp"
    _write_minimal_vendored_codebase_source(source)
    binary = source / "build" / "c" / "codebase-memory-mcp"
    binary.parent.mkdir(parents=True)
    binary.write_text("placeholder", encoding="utf-8")
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        codebase_source_dir=source,
        codebase_binary_path=binary,
    )

    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"ok":true,"project":"ignored"}',
        stderr="",
    )
    with patch("evermind_mcp.vendored_codebase.subprocess.run", return_value=completed) as run:
        result = CodebaseEngine(cfg).call(
            "index_repository",
            {"repo_path": str(tmp_path), "project": "display-name"},
        )

    command = run.call_args.args[0]
    assert command == [str(binary), "cli", "--json", "index_repository"]
    assert json.loads(run.call_args.kwargs["input"])["name"] == result["workspace_id"]
    assert not any(argument.startswith("{") for argument in command)


def test_codebase_native_engine_detect_changes_resolves_project_from_repo_path(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def alpha():\n    return 'ok'\n", encoding="utf-8")
    cfg = _native_only_config(tmp_path)
    engine = CodebaseEngine(cfg)

    with patch.dict(os.environ, {"PATH": ""}, clear=False):
        indexed = engine.call("index_repository", {"repo_path": str(repo), "project": "explicit-project"})
        changes = engine.call("detect_changes", {"repo_path": str(repo)})

    assert indexed["project"] == "explicit-project"
    assert changes["ok"] is True
    assert changes["changed_files"] == []


def test_archive_bridge_list_workspaces_local_does_not_require_cloud(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path,
        default_space="coding:test",
    )
    bridge = ArchiveBridge(cfg)

    result = bridge.call("list_workspaces", {"local": True})

    assert result["ok"] is True
    assert result["engine"] == "evermind-archive"
    assert result["native"] is True
    assert result["workspaces"] == []
    assert result["cloud_available"] is False
    assert result["reason"] == "local_mode_no_cloud"
    assert result["backend"] == "source-fused-basic-memory"
    assert result["source_integrated"] in {True, False}


def test_archive_bridge_cloud_flag_is_local_only_without_external_cli(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)

    with patch.dict(os.environ, {"PATH": ""}, clear=False):
        written = bridge.call(
            "write_note",
            {
                "title": "Cloud Flag Note",
                "folder": "eval",
                "content": "local archive content",
                "project": "sample",
                "cloud": True,
                "overwrite": True,
            },
        )
        read = bridge.call(
            "read_note",
            {
                "identifier": "eval/cloud-flag-note",
                "project": "sample",
                "cloud": True,
            },
        )
        search = bridge.call(
            "search_notes",
            {
                "query": "local archive",
                "project": "sample",
                "cloud": True,
            },
        )

    assert written["ok"] is True
    assert written["engine"] == "evermind-archive"
    assert written["native"] is True
    assert written["fast_path"] is True
    assert written["cloud_requested"] is True
    assert written["cloud_disabled"] is True
    assert written["route"] == "local"
    assert read["ok"] is True
    assert "local archive content" in read["content"]
    assert search["count"] == 1


def test_archive_local_only_surface_does_not_require_external_cli(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)

    with patch.dict(os.environ, {"PATH": ""}, clear=False):
        written = bridge.call(
            "write_note",
            {
                "title": "Surface Note",
                "folder": "eval",
                "content": "surface needle",
                "project": "sample",
                "cloud": True,
                "overwrite": True,
                "tags": ["surface"],
            },
        )
        calls = {
            "read_note": bridge.call(
                "read_note",
                {"identifier": "eval/surface-note", "project": "sample", "cloud": True},
            ),
            "edit_note": bridge.call(
                "edit_note",
                {
                    "identifier": "eval/surface-note",
                    "operation": "append",
                    "content": "surface append",
                    "project": "sample",
                    "cloud": True,
                },
            ),
            "build_context": bridge.call(
                "build_context",
                {
                    "url": "memory://eval/surface-note",
                    "project": "sample",
                    "cloud": True,
                },
            ),
            "recent_activity": bridge.call(
                "recent_activity",
                {"project": "sample", "cloud": True},
            ),
            "search_notes": bridge.call(
                "search_notes",
                {"query": "surface", "project": "sample", "cloud": True},
            ),
            "list_memory_projects": bridge.call("list_memory_projects", {"cloud": True}),
            "list_workspaces": bridge.call("list_workspaces", {"cloud": True}),
            "schema_validate": bridge.call(
                "schema_validate",
                {"project": "sample", "cloud": True},
            ),
            "schema_infer": bridge.call(
                "schema_infer",
                {"note_type": "note", "project": "sample", "cloud": True},
            ),
            "schema_diff": bridge.call(
                "schema_diff",
                {"note_type": "note", "project": "sample", "cloud": True},
            ),
        }
        deleted = bridge.call(
            "delete_note",
            {"identifier": "eval/surface-note", "project": "sample", "cloud": True},
        )

    assert written["ok"] is True
    assert all(result["ok"] for result in calls.values())
    assert deleted["ok"] is True
    assert deleted["deleted"] is True
    assert all(
        result["engine"] == "evermind-archive"
        and result["native"] is True
        and result["fast_path"] is True
        and result["route"] == "local"
        for result in [written, *calls.values(), deleted]
    )
    assert all(result["cloud_disabled"] is True for result in [written, *calls.values(), deleted])


def test_archive_fast_path_reads_writes_and_searches_without_cli(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)

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
    assert written["engine"] == "evermind-archive"
    assert written["native"] is True
    assert written["fast_path"] is True
    assert read["content"].startswith("# Eval Note")
    assert search["count"] == 1
    assert projects["projects"][0]["name"] == "sample"


def test_archive_fast_path_extracts_basic_memory_style_context(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)

    primary = bridge.call(
        "write_note",
        {
            "title": "Alpha Memory",
            "folder": "eval",
            "content": "## Observations\n- local graph keeps call edges\n\nRelated: [[Beta Memory]]",
            "project": "sample",
            "overwrite": True,
            "tags": ["memory", "codebase"],
            "type": "decision",
        },
    )
    bridge.call(
        "write_note",
        {
            "title": "Beta Memory",
            "folder": "eval",
            "content": "Backlink to [[Alpha Memory]]",
            "project": "sample",
            "overwrite": True,
            "tags": ["memory"],
        },
    )

    search = bridge.call(
        "search_notes",
        {"query": "call edges", "project": "sample", "tags": ["memory"], "type": "decision"},
    )
    context = bridge.call("build_context", {"url": f"memory://{primary['identifier']}", "project": "sample"})

    assert search["count"] == 1
    result = search["results"][0]
    assert result["type"] == "decision"
    assert result["tags"] == ["memory", "codebase"]
    assert result["relations"][0]["target"] == "Beta Memory"
    assert "local graph keeps call edges" in result["observations"]
    assert context["backlinks"][0]["title"] == "Beta Memory"
    assert context["related"][0]["identifier"] == "eval/beta-memory"


def test_builtin_engines_ignore_external_commands_on_path(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "external-command-called.txt"
    for command_name in ("codebase-memory-mcp", "basic-memory"):
        shell_script = fake_bin / command_name
        shell_script.write_text(f"#!/usr/bin/env sh\necho called >> '{marker.as_posix()}'\nexit 42\n", encoding="utf-8")
        shell_script.chmod(0o755)
        cmd_script = fake_bin / f"{command_name}.cmd"
        cmd_script.write_text(f"@echo off\r\necho called >> \"{marker}\"\r\nexit /b 42\r\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def alpha():\n    return 'needle'\n", encoding="utf-8")
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )

    with patch.dict(os.environ, {"PATH": str(fake_bin)}, clear=False):
        indexed = CodebaseEngine(cfg).call("index_repository", {"repo_path": str(repo)})
        written = ArchiveBridge(cfg).call(
            "write_note",
            {
                "title": "Path Isolation",
                "folder": "eval",
                "content": "archive content",
                "project": "sample",
                "overwrite": True,
            },
        )

    assert indexed["ok"] is True
    assert indexed["engine"] == "evermind-code-graph"
    assert written["ok"] is True
    assert written["engine"] == "evermind-archive"
    assert not marker.exists()


def test_archive_fast_path_write_identifier_round_trips_without_project(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)

    written = bridge.call(
        "write_note",
        {
            "title": "Round Trip Note",
            "folder": "eval",
            "content": "round trip content",
            "project": "sample",
            "overwrite": True,
        },
    )
    read = bridge.call("read_note", {"identifier": written["identifier"]})

    assert written["identifier"] == "sample/eval/round-trip-note"
    assert read["ok"] is True
    assert "round trip content" in read["content"]


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


def test_archive_fast_path_lock_permission_error_is_retried(tmp_path, monkeypatch):
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
            "title": "Windows Lock",
            "folder": "eval",
            "content": "base",
            "project": "sample",
            "overwrite": True,
        },
    )

    real_open = archive_bridge.os.open
    calls = 0

    def flaky_open(path, flags, mode=0o777, *, dir_fd=None):
        nonlocal calls
        if str(path).endswith(".lock") and calls == 0:
            calls += 1
            Path(path).write_text("held", encoding="utf-8")
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(archive_bridge.os, "open", flaky_open)
    monkeypatch.setattr(
        archive_bridge.time,
        "sleep",
        lambda _seconds: [
            lock.unlink()
            for lock in (tmp_path / "archive").rglob("*.lock")
            if lock.read_text(encoding="utf-8") == "held"
        ],
    )

    result = bridge.call(
        "edit_note",
        {
            "identifier": "eval/windows-lock",
            "operation": "append",
            "content": "after retry",
            "project": "sample",
        },
    )
    read = bridge.call("read_note", {"identifier": "eval/windows-lock", "project": "sample"})

    assert result["ok"] is True
    assert calls == 1
    assert "after retry" in read["content"]


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


def test_archive_source_fusion_metadata_exposes_basic_memory_license(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)

    metadata = bridge.metadata()
    result = bridge.call("list_workspaces", {})

    assert metadata["backend"] == "source-fused-basic-memory"
    assert metadata["license"] == "AGPL-3.0-or-later"
    assert metadata["bridge_runtime_allowed"] is False
    assert "basic-memory" in metadata["source_path"]
    assert result["backend"] == metadata["backend"]
    assert result["license"] == metadata["license"]


@pytest.mark.asyncio
async def test_status_health_expose_local_provider_boundary(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        embed_enabled=False,
        rerank_enabled=False,
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    svc = MemoryService(cfg)

    status = await svc.status()
    health = await svc.health()

    for result in (status, health):
        assert result["provider_boundary"] == {
            "mode": "local",
            "sync_mode": "off",
            "cloud_enabled": False,
            "bridge_runtime_allowed": False,
            "code_graph_provider": "source-fused",
            "archive_provider": "source-fused",
        }
        assert result["archive_backend"] == "source-fused-basic-memory"
        assert result["archive_license"] == "AGPL-3.0-or-later"


def test_archive_soak_64_concurrent_appends_preserve_all_lines(tmp_path):
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
            "title": "Soak Note",
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
                "identifier": "eval/soak-note",
                "operation": "append",
                "content": f"soak-line-{index}",
                "project": "sample",
            },
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(append_line, range(64)))

    read = bridge.call("read_note", {"identifier": "eval/soak-note", "project": "sample"})

    assert all(item["ok"] for item in results)
    for index in range(64):
        assert f"soak-line-{index}" in read["content"]


def test_codebase_large_repo_pressure_indexes_500_files_without_external_binary(tmp_path):
    repo = tmp_path / "large-repo"
    repo.mkdir()
    for index in range(500):
        (repo / f"module_{index:03d}.py").write_text(
            f"def fn_{index:03d}():\n    return 'needle-{index:03d}'\n",
            encoding="utf-8",
        )
    cfg = _native_only_config(tmp_path)
    engine = CodebaseEngine(cfg)

    with patch.dict(os.environ, {"PATH": ""}, clear=False):
        indexed = engine.call("index_repository", {"repo_path": str(repo), "project": "large"})
        search = engine.call("search_code", {"project": "large", "pattern": "needle-499"})

    assert indexed["ok"] is True
    assert indexed["files_indexed"] == 500
    assert indexed["fallback"] == "native"
    assert search["ok"] is True
    assert search["total_results"] == 1
