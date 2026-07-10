from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from evermind_mcp.config_v2 import EverMindConfig
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


@pytest.mark.asyncio
async def test_server_dispatches_codebase_tools(tmp_path, monkeypatch):
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
    codebase = _parse(
        await server_mod.call_tool(
            "search_code",
            {"project": "D-Project-EverMind", "pattern": "server_v2"},
        )
    )
    assert codebase["engine"] == "evermind-code-graph"
    assert codebase["tool"] == "search_code"
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


def test_archive_source_fusion_metadata_exposes_basic_memory_license(tmp_path):
    cfg = EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )
    bridge = ArchiveBridge(cfg)

    metadata = bridge.metadata()

    assert metadata["backend"] == "source-fused-basic-memory"
    assert metadata["license"] == "AGPL-3.0-or-later"
    assert metadata["bridge_runtime_allowed"] is False
    assert "basic-memory" in metadata["source_path"]


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
