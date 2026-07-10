from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import multiprocessing
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path

import pytest
from mcp import types

import evermind_mcp.archive_bridge as archive_bridge
import evermind_mcp.config_v2 as config_v2
from evermind_mcp.archive_bridge import ArchiveBridge
from evermind_mcp.codebase_engine import CodebaseEngine
from evermind_mcp.config_v2 import EverMindConfig
from evermind_mcp.memory_service_v2 import MemoryService
from evermind_mcp.legacy_migration import LegacyCatalogMigrator
from evermind_mcp.storage import EmbeddedStorage


ROOT = Path(__file__).resolve().parents[2]


def _source_tree_stats(root: Path, manifest: dict) -> tuple[int, int, str]:
    tree_config = manifest["tree_hash"]
    excluded_names = set(tree_config["excluded_names"])
    excluded_files = tuple(tree_config["excluded_files"])
    records: list[tuple[str, str, int]] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if any(part in excluded_names for part in relative.split("/")):
            continue
        if any(fnmatch.fnmatch(relative, pattern) for pattern in excluded_files):
            continue
        records.append(
            (
                relative,
                hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_size,
            )
        )

    records.sort(key=lambda item: item[0])
    tree = hashlib.sha256(
        "".join(f"{digest}  {relative}\n" for relative, digest, _ in records).encode()
    ).hexdigest()
    return len(records), sum(size for _, _, size in records), tree


def _config(tmp_path: Path, *, space: str = "coding:test") -> EverMindConfig:
    return EverMindConfig(
        home=tmp_path / "home",
        default_space=space,
        embed_enabled=False,
        embed_warmup_on_start=False,
        rerank_enabled=False,
        archive_root=tmp_path / "archive",
        archive_candidate_dir=tmp_path / "archive" / ".candidates",
    )


def _vendored_config(tmp_path: Path) -> EverMindConfig:
    source = ROOT / "third_party" / "codebase-memory-mcp"
    return EverMindConfig(
        home=tmp_path / "home",
        default_space="coding:test",
        embed_enabled=False,
        embed_warmup_on_start=False,
        rerank_enabled=False,
        codebase_source_dir=source,
        codebase_binary_path=source / "build" / "c" / "codebase-memory-mcp.exe",
        codebase_cli_timeout_seconds=60,
    )


def _set_isolated_codebase_environment(monkeypatch, tmp_path: Path) -> None:
    for key, leaf in (
        ("LOCALAPPDATA", "localappdata"),
        ("APPDATA", "appdata"),
        ("HOME", "home-env"),
        ("USERPROFILE", "userprofile"),
    ):
        path = tmp_path / leaf
        path.mkdir()
        monkeypatch.setenv(key, str(path))
    monkeypatch.setenv("CBM_INDEX_SUPERVISOR", "1")
    monkeypatch.setenv("CBM_INDEX_MAX_RESTARTS", "8")


def _remember_in_process(home: str, index: int, start, results) -> None:
    config = EverMindConfig(
        home=Path(home),
        default_space=f"coding:atomic-{index}",
        embed_enabled=False,
        embed_warmup_on_start=False,
        rerank_enabled=False,
    )
    service = MemoryService(config)
    try:
        start.wait(timeout=10)
        result = asyncio.run(
            service.remember(
                "globally identical atomic memory",
                importance=1,
                meta={"writer": index},
            )
        )
        results.put({"ok": True, "result": result})
    except Exception as exc:
        results.put({"ok": False, "error": repr(exc)})
    finally:
        service.storage.close_all()


def test_package_metadata_matches_local_source_fusion_contract() -> None:
    project = tomllib.loads(
        (ROOT / "mcp" / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]

    assert project["requires-python"] == ">=3.12"
    assert project["license"] == "AGPL-3.0-or-later"
    assert (
        "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)"
        in project["classifiers"]
    )
    assert "mcp==1.26.0" in project["dependencies"]
    assert "fastmcp==3.3.1" in project["dependencies"]


def test_vendored_source_manifest_pins_exact_upstream_commits() -> None:
    path = ROOT / "third_party" / "source-manifest.json"
    assert path.is_file()
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert manifest["basic_memory"]["version"] == "0.22.1"
    assert (
        manifest["basic_memory"]["commit"] == "0e59bbffaf7dbca8f0507d1c8cc15033332670ee"
    )
    assert manifest["basic_memory"]["upstream_git_tree"] == (
        "1fbf6b2a8b4136f000b2dd579a03a9bbdd1eda26"
    )
    assert manifest["codebase_memory_mcp"]["version"] == "0.8.1"
    assert manifest["codebase_memory_mcp"]["commit"] == (
        "c3bee33d543a592c63aebf11333090c37868c1c6"
    )
    assert manifest["codebase_memory_mcp"]["upstream_git_tree"] == (
        "0a8ad8345d0aec264d04ccd8453c5c75bf4c79dc"
    )
    assert manifest["codebase_memory_mcp"]["local_overlays"]
    assert manifest["codebase_memory_mcp"]["binary_sha256"]


def test_vendored_source_manifest_matches_current_source_trees() -> None:
    manifest = json.loads(
        (ROOT / "third_party" / "source-manifest.json").read_text(encoding="utf-8")
    )

    for key, source in (
        ("basic_memory", ROOT / "third_party" / "basic-memory"),
        ("codebase_memory_mcp", ROOT / "third_party" / "codebase-memory-mcp"),
    ):
        expected = manifest[key]
        actual = _source_tree_stats(source, manifest)
        assert actual == (
            expected["file_count"],
            expected["source_bytes"],
            expected["tree_sha256"],
        )


def test_vendored_manifest_matches_binary_and_offline_fixture() -> None:
    manifest = json.loads(
        (ROOT / "third_party" / "source-manifest.json").read_text(encoding="utf-8")
    )
    codebase = manifest["codebase_memory_mcp"]
    binary = ROOT / "third_party" / codebase["binary_path"]
    fixture_overlay = next(
        overlay
        for overlay in codebase["local_overlays"]
        if overlay["id"] == "offline_fastapi_incremental_fixture"
    )
    fixture_meta = fixture_overlay["fixture"]
    fixture = ROOT / "third_party" / "codebase-memory-mcp" / fixture_overlay["paths"][0]

    assert binary.stat().st_size == codebase["binary_bytes"]
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == codebase["binary_sha256"]
    assert fixture.stat().st_size == fixture_meta["bytes"]
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == fixture_meta["sha256"]
    assert codebase["invocation_protocol"] == {
        "argv": ["<binary>", "cli", "--json", "<tool>"],
        "arguments_transport": "stdin-json",
        "deprecated_raw_json_argv": False,
    }


def test_candidate_commit_cannot_escape_archive_root(tmp_path: Path) -> None:
    bridge = ArchiveBridge(_config(tmp_path))
    outside = tmp_path / "outside.md"
    candidate = bridge.propose_update(
        project_slug="safe-project",
        target_file=str(outside.resolve()),
        content="must stay inside the archive",
    )

    result = (
        candidate
        if candidate.get("ok") is False
        else bridge.commit_update(candidate["candidate_id"], confirmed=True)
    )

    assert result["ok"] is False
    assert result["code"] == "ARCHIVE_INVALID_ARGUMENT"
    assert not outside.exists()


def test_candidate_id_cannot_escape_candidate_directory(tmp_path: Path) -> None:
    bridge = ArchiveBridge(_config(tmp_path))
    outside_candidate = tmp_path / "archive" / "forged.json"
    outside_target = tmp_path / "forged-output.md"
    outside_candidate.parent.mkdir(parents=True)
    outside_candidate.write_text(
        json.dumps(
            {
                "candidate_id": "../forged",
                "project_slug": "safe-project",
                "target_file": str(outside_target.resolve()),
                "content": "forged",
                "evidence": "",
                "reason": "",
            }
        ),
        encoding="utf-8",
    )

    result = bridge.commit_update("../forged", confirmed=True)

    assert result["ok"] is False
    assert result["code"] == "ARCHIVE_INVALID_ARGUMENT"
    assert not outside_target.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("not_a_tool", {}),
        ("read_note", {"identifier": "missing", "project": "test"}),
    ],
)
async def test_application_failure_sets_mcp_is_error(
    tmp_path: Path,
    monkeypatch,
    tool_name: str,
    arguments: dict,
) -> None:
    import evermind_mcp.server_v2 as server_mod

    service = MemoryService(_config(tmp_path))
    server_mod._svc = service
    monkeypatch.setattr(
        server_mod, "_maybe_update_space_from_roots", lambda: asyncio.sleep(0)
    )
    request = types.CallToolRequest(
        params=types.CallToolRequestParams(name=tool_name, arguments=arguments)
    )
    try:
        response = await server_mod.server.request_handlers[types.CallToolRequest](
            request
        )
        assert response.root.isError is True
    finally:
        server_mod._svc = None
        service.storage.close_all()


def test_memory_service_close_stops_its_workers(tmp_path: Path) -> None:
    before = set(threading.enumerate())
    service = MemoryService(_config(tmp_path))
    try:
        close = getattr(service, "close", None)
        assert callable(close)
        close()
        service_threads = {
            thread
            for thread in threading.enumerate()
            if thread not in before
            and thread.name in {"evermind-briefing", "evermind-embed"}
        }
        assert not service_threads
    finally:
        service.storage.close_all()


def test_archive_lock_recovers_immediately_when_owner_is_dead(tmp_path: Path) -> None:
    note = tmp_path / "archive" / "projects" / "sample" / "note.md"
    note.parent.mkdir(parents=True)
    lock = note.with_name(note.name + ".lock")
    lock.write_text(
        json.dumps({"pid": 2_147_483_647, "created_at": time.time()}),
        encoding="utf-8",
    )

    acquired = False
    try:
        with archive_bridge._file_lock(note, timeout_seconds=0.1):
            acquired = True
    except TimeoutError:
        pass

    assert acquired
    assert not lock.exists()


@pytest.mark.asyncio
async def test_default_recall_reads_other_projects_with_provenance(
    tmp_path: Path,
) -> None:
    service = MemoryService(_config(tmp_path, space="coding:alpha"))
    try:
        await service.remember("cross project zephyr fact", importance=1)
        service.set_space("coding:beta")

        result = await service.recall(
            "zephyr",
            mode="fts",
            all_spaces=False,
            min_score=0,
        )

        items = result.get("memories") or result.get("results") or []
        match = next((item for item in items if "zephyr" in item["content"]), None)
        assert match is not None
        assert match["source_projects"] == ["coding:alpha"]

        listed = await service.list_memories(limit=20)
        listed_match = next(
            item for item in listed["memories"] if "zephyr" in item["content"]
        )
        assert listed_match["source_projects"] == ["coding:alpha"]

        all_spaces_result = await service.recall(
            "zephyr",
            mode="fts",
            all_spaces=True,
            min_score=0,
        )
        all_spaces_items = all_spaces_result.get("results") or []
        assert {item["id"] for item in all_spaces_items} == {
            item["id"] for item in items
        }
    finally:
        service.storage.close_all()


def test_catalog_schema_enforces_global_identity_and_fact_history(
    tmp_path: Path,
) -> None:
    service = MemoryService(_config(tmp_path))
    try:
        columns = {
            row[1]
            for row in service.storage.conn.execute(
                "PRAGMA table_info(memories)"
            ).fetchall()
        }
        tables = {
            row[0]
            for row in service.storage.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        assert {
            "normalized_hash",
            "state",
            "valid_from",
            "valid_to",
            "supersedes_id",
        } <= columns
        assert {
            "projects",
            "workspaces",
            "memory_sources",
            "memory_conflicts",
            "memory_conflict_members",
            "embedding_profiles",
            "memory_embeddings",
            "project_operations",
            "legacy_memory_map",
            "basic_project_bindings",
        } <= tables
    finally:
        service.storage.close_all()


def test_four_process_exact_dedup_keeps_one_memory_and_all_sources(
    tmp_path: Path,
) -> None:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=_remember_in_process,
            args=(str(tmp_path / "home"), index, start, results),
        )
        for index in range(4)
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=20)
        assert not process.is_alive()
        assert process.exitcode == 0
    writes = [results.get(timeout=5) for _ in processes]
    assert all(write["ok"] for write in writes), writes

    service = MemoryService(_config(tmp_path, space="coding:atomic-0"))
    try:
        tables = {
            row[0]
            for row in service.storage.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "memory_sources" in tables
        memory_count = service.storage.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE content=?",
            ("globally identical atomic memory",),
        ).fetchone()[0]
        source_count = service.storage.conn.execute(
            "SELECT COUNT(DISTINCT source.project_id) "
            "FROM memory_sources AS source "
            "JOIN memories AS memory ON memory.id=source.memory_id "
            "WHERE memory.content=?",
            ("globally identical atomic memory",),
        ).fetchone()[0]
        assert memory_count == 1
        assert source_count == 4
    finally:
        service.storage.close_all()


def test_legacy_space_databases_migrate_once_with_backups_and_valid_references(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, space="coding:alpha")
    config.home.mkdir(parents=True)
    legacy_ids: list[str] = []
    for space in ("coding:alpha", "coding:beta"):
        legacy_path = config.legacy_db_path(space)
        legacy = EmbeddedStorage(legacy_path)
        memory = legacy.insert_memory(
            space=space,
            content="shared legacy migration fact",
            importance=1,
            tags=[space],
        )
        legacy_ids.append(memory.id)
        legacy.link_memory_to_entities(memory.id, space, ["LegacyMigration"])
        legacy.log_event(space, "remember", memory.id, {"legacy": True})
        legacy.close_all()

    service = MemoryService(config)
    try:
        conn = service.storage.conn
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM memories WHERE content='shared legacy migration fact'"
            ).fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT COUNT(DISTINCT project_id) FROM memory_sources"
            ).fetchone()[0]
            == 2
        )
        assert conn.execute("SELECT COUNT(*) FROM legacy_memory_map").fetchone()[0] == 2
        assert (
            conn.execute(
                """
            SELECT COUNT(*) FROM event_log event
            LEFT JOIN memories memory ON memory.id=event.memory_id
            WHERE event.memory_id IS NOT NULL AND memory.id IS NULL
            """
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                """
            SELECT COUNT(*) FROM graph_edges edge
            LEFT JOIN memories memory
              ON memory.id=json_extract(edge.meta, '$.memory_id')
            WHERE json_extract(edge.meta, '$.memory_id') IS NOT NULL
              AND memory.id IS NULL
            """
            ).fetchone()[0]
            == 0
        )
        assert {path.name for path in (config.home / "backups").glob("*.bak")} == {
            f"{config.legacy_db_path(space).name}.bak"
            for space in ("coding:alpha", "coding:beta")
        }
        first_counts = tuple(
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("memories", "memory_sources", "event_log", "graph_edges")
        )
    finally:
        service.close()

    restarted = MemoryService(config)
    try:
        second_counts = tuple(
            restarted.storage.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[
                0
            ]
            for table in ("memories", "memory_sources", "event_log", "graph_edges")
        )
        assert second_counts == first_counts
        assert {
            row["legacy_id"]
            for row in restarted.storage.conn.execute(
                "SELECT legacy_id FROM legacy_memory_map"
            ).fetchall()
        } == set(legacy_ids)
    finally:
        restarted.close()


def test_interrupted_legacy_migration_resumes_from_durable_memory_map(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path, space="coding:resume")
    config.home.mkdir(parents=True)
    legacy = EmbeddedStorage(config.legacy_db_path("coding:resume"))
    memory = legacy.insert_memory(
        "coding:resume",
        "interrupted migration memory",
        importance=1,
    )
    legacy.link_memory_to_entities(memory.id, "coding:resume", ["MigrationResume"])
    legacy.log_event("coding:resume", "remember", memory.id, {"resume": True})
    legacy.close_all()

    catalog = EmbeddedStorage(config.db_path(config.default_space))
    migrator = LegacyCatalogMigrator(config.home, catalog)

    def crash_after_memories(*_args, **_kwargs):
        raise RuntimeError("injected migration interruption")

    monkeypatch.setattr(migrator, "_import_graph", crash_after_memories)
    with pytest.raises(RuntimeError, match="injected migration interruption"):
        migrator.migrate()
    assert catalog.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1
    assert (
        catalog.conn.execute("SELECT COUNT(*) FROM legacy_memory_map").fetchone()[0]
        == 1
    )
    assert (
        catalog.conn.execute(
            "SELECT state FROM project_operations WHERE kind='legacy_migration'"
        ).fetchone()[0]
        == "running"
    )
    catalog.close_all()

    recovered = EmbeddedStorage(config.db_path(config.default_space))
    try:
        LegacyCatalogMigrator(config.home, recovered).migrate()
        assert (
            recovered.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1
        )
        assert (
            recovered.conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
            == 1
        )
        assert (
            recovered.conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0] == 1
        )
        assert (
            recovered.conn.execute(
                "SELECT state FROM project_operations WHERE kind='legacy_migration'"
            ).fetchone()[0]
            == "completed"
        )
    finally:
        recovered.close_all()


def test_unified_project_resolver_normalizes_remotes_and_isolates_workspaces(
    tmp_path: Path,
) -> None:
    repos = [tmp_path / name / "shared" for name in ("first", "second", "third")]
    remotes = (
        "git@github.com:Example/Unified.git",
        "https://github.com/example/unified.git",
        "https://github.com/other/unified.git",
    )
    for repo, remote in zip(repos, remotes, strict=True):
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "remote", "add", "origin", remote],
            check=True,
        )

    service = MemoryService(_config(tmp_path, space="coding:resolver"))
    try:
        assert hasattr(service, "projects")
        first = service.projects.resolve_workspace(repos[0])
        second = service.projects.resolve_workspace(repos[1])
        third = service.projects.resolve_workspace(repos[2])

        assert first["project_id"] == second["project_id"]
        assert first["workspace_id"] != second["workspace_id"]
        assert third["project_id"] != first["project_id"]
        assert third["workspace_id"] not in {
            first["workspace_id"],
            second["workspace_id"],
        }
        assert (
            service.storage.conn.execute(
                """
            SELECT COUNT(*) FROM project_operations
            WHERE kind='create_project' AND state='completed'
            """
            ).fetchone()[0]
            == 3
        )
    finally:
        service.close()


@pytest.mark.asyncio
async def test_unified_delete_uses_aliases_journal_and_preserves_durable_data(
    tmp_path: Path, monkeypatch
) -> None:
    config = _config(tmp_path, space="coding:delete")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "remote",
            "add",
            "origin",
            "https://github.com/example/delete-target.git",
        ],
        check=True,
    )
    archive_note = config.archive_root / "projects" / "delete-target" / "kept.md"
    archive_note.parent.mkdir(parents=True)
    archive_note.write_text("durable archive", encoding="utf-8")

    service = MemoryService(config)
    calls: list[tuple[str, dict]] = []
    try:
        resolved = service.projects.resolve_workspace(repo)
        project_id = resolved["project_id"]
        service.storage.insert_memory(
            project_id,
            "durable memory survives unified detach",
            importance=2,
        )
        service.storage.conn.execute(
            """
            INSERT INTO basic_project_bindings
                (project_id, basic_external_id, basic_name, basic_path, updated_at)
            VALUES (?, 'basic-1', 'delete-target', ?, ?)
            """,
            (project_id, str(archive_note.parent), int(time.time() * 1000)),
        )
        service.storage.conn.commit()

        def fake_codebase_call(tool: str, arguments: dict) -> dict:
            calls.append((tool, arguments))
            return {"ok": True, "status": "deleted", "project": arguments["project"]}

        monkeypatch.setattr(service.codebase, "call", fake_codebase_call)

        missing = await service.delete_project()
        assert missing["ok"] is False
        assert missing["code"] == "PROJECT_IDENTIFIER_REQUIRED"

        other = service.projects.resolve_workspace(tmp_path / "other")
        mismatched = await service.delete_project(
            project=project_id,
            project_name=other["project_id"],
        )
        assert mismatched["ok"] is False
        assert mismatched["code"] == "PROJECT_IDENTIFIER_MISMATCH"

        result = await service.delete_project(
            project=project_id,
            project_name="delete-target",
        )
        assert result["ok"] is True
        assert result["project_id"] == project_id
        assert calls == [("delete_project", {"project": resolved["workspace_id"]})]
        assert (
            service.storage.conn.execute(
                "SELECT state FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()[0]
            == "detached"
        )
        assert (
            service.storage.conn.execute(
                "SELECT state FROM workspaces WHERE workspace_id=?",
                (resolved["workspace_id"],),
            ).fetchone()[0]
            == "detached"
        )
        assert (
            service.storage.conn.execute(
                "SELECT COUNT(*) FROM basic_project_bindings WHERE project_id=?",
                (project_id,),
            ).fetchone()[0]
            == 0
        )
        assert (
            service.storage.conn.execute(
                "SELECT COUNT(*) FROM memories WHERE content=?",
                ("durable memory survives unified detach",),
            ).fetchone()[0]
            == 1
        )
        assert (
            service.storage.conn.execute(
                "SELECT state FROM project_operations WHERE kind='delete_project'"
            ).fetchone()[0]
            == "completed"
        )
        assert repo.is_dir()
        assert archive_note.read_text(encoding="utf-8") == "durable archive"
    finally:
        service.close()


@pytest.mark.asyncio
async def test_unified_delete_resumes_only_unfinished_workspace_steps(
    tmp_path: Path, monkeypatch
) -> None:
    service = MemoryService(_config(tmp_path, space="coding:delete-resume"))
    try:
        repos = [tmp_path / name for name in ("checkout-a", "checkout-b")]
        for repo in repos:
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/example/resumable-delete.git",
                ],
                check=True,
            )
        resolved = [service.projects.resolve_workspace(repo) for repo in repos]
        project_id = resolved[0]["project_id"]
        first_calls: list[str] = []

        def fail_second(_tool: str, arguments: dict) -> dict:
            first_calls.append(arguments["project"])
            if len(first_calls) == 2:
                return {"ok": False, "code": "INJECTED_FAILURE"}
            return {"ok": True}

        monkeypatch.setattr(service.codebase, "call", fail_second)
        failed = await service.delete_project(project=project_id)
        assert failed["ok"] is False
        assert len(first_calls) == 2

        resumed_calls: list[str] = []

        def succeed(_tool: str, arguments: dict) -> dict:
            resumed_calls.append(arguments["project"])
            return {"ok": True}

        monkeypatch.setattr(service.codebase, "call", succeed)
        resumed = await service.delete_project(project=project_id)
        assert resumed["ok"] is True
        assert resumed_calls == [first_calls[1]]
    finally:
        service.close()


@pytest.mark.asyncio
async def test_code_index_and_memory_write_share_one_catalog_project(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "workspace"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "remote",
            "add",
            "origin",
            "git@github.com:example/shared-lifecycle.git",
        ],
        check=True,
    )
    service = MemoryService(_config(tmp_path, space="coding:before-index"))
    try:
        monkeypatch.setattr(
            service.codebase,
            "call",
            lambda tool, arguments: {
                "ok": True,
                "tool": tool,
                "project": arguments["project"],
            },
        )
        indexed = service.call_codebase("index_repository", {"repo_path": str(repo)})
        remembered = await service.remember(
            "one project lifecycle memory", importance=1
        )
        archived = service.call_archive(
            "write_note",
            {
                "title": "Unified Lifecycle",
                "folder": "decisions",
                "content": "one project archive",
                "overwrite": True,
            },
        )

        assert service.space == indexed["project_id"]
        assert service.storage.source_projects(remembered["id"]) == [
            indexed["project_id"]
        ]
        assert archived["ok"] is True
        assert f"/projects/{indexed['project_id']}/" in archived["path"].replace(
            "\\", "/"
        )
        workspace = service.storage.conn.execute(
            "SELECT project_id FROM workspaces WHERE workspace_id=?",
            (indexed["workspace_id"],),
        ).fetchone()
        assert workspace["project_id"] == indexed["project_id"]
        binding = service.storage.conn.execute(
            "SELECT * FROM basic_project_bindings WHERE project_id=?",
            (indexed["project_id"],),
        ).fetchone()
        assert binding["basic_external_id"] == indexed["project_id"]
        assert (
            Path(binding["basic_path"]).resolve()
            in Path(archived["path"]).resolve().parents
        )
    finally:
        service.close()


@pytest.mark.xfail(strict=True, reason="no-key startup disables semantic retrieval")
def test_local_embedding_is_enabled_without_external_api(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(config_v2, "_load_dotenv_files", lambda _cwd=None: None)
    monkeypatch.setenv("EVERMIND_HOME", str(tmp_path / "home"))
    for key in (
        "EVERMIND_SILICONFLOW_API_KEY",
        "SILICONFLOW_API_KEY",
        "EVERMIND_EMBED_API_KEY",
        "EVERMIND_LLM_API_KEY",
        "EVERMIND_EMBED_ENABLED",
        "EVERMIND_EMBED_PROVIDER",
        "EVERMIND_EMBED_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)

    config = config_v2.load_config(str(tmp_path))

    assert config.embed_enabled is True
    assert config.embed_provider == "auto"


@pytest.mark.asyncio
async def test_target_local_mcp_surface_is_exactly_50_tools() -> None:
    import evermind_mcp.server_v2 as server_mod

    names = {tool.name for tool in await server_mod.mcp.list_tools()}
    compatible_local = {
        "build_context",
        "canvas",
        "create_memory_project",
        "delete_note",
        "delete_project",
        "edit_note",
        "fetch",
        "list_directory",
        "list_memory_projects",
        "move_note",
        "read_content",
        "read_note",
        "recent_activity",
        "release_notes",
        "schema_diff",
        "schema_infer",
        "schema_validate",
        "search",
        "search_notes",
        "view_note",
        "write_note",
    }

    assert len(names) == 50
    assert compatible_local <= names
    assert {"cloud_info", "list_workspaces"}.isdisjoint(names)
    assert len(await server_mod.mcp.list_prompts()) == 3
    assert {str(resource.uri) for resource in await server_mod.mcp.list_resources()} == {
        "memory://ai_assistant_guide"
    }
    assert {
        template.uri_template
        for template in await server_mod.mcp.list_resource_templates()
    } == {"memory://{project}/info"}
    assert any(name.startswith("basic_memory") for name in sys.modules)


@pytest.mark.asyncio
async def test_real_stdio_exposes_the_unified_local_surface(tmp_path: Path) -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(tmp_path / "home"),
        EVERMIND_DEFAULT_SPACE="stdio:surface",
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from evermind_mcp.server_v2 import main_sync; main_sync()",
        ],
        env=env,
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            assert len((await session.list_tools()).tools) == 50
            assert len((await session.list_prompts()).prompts) == 3
            assert len((await session.list_resources()).resources) == 1
            assert len((await session.list_resource_templates()).resourceTemplates) == 1


@pytest.mark.asyncio
async def test_real_stdio_executes_basic_memory_locally_when_cloud_env_is_set(
    tmp_path: Path,
) -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    archive_root = tmp_path / "archive"
    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(tmp_path / "home"),
        EVERMIND_DEFAULT_SPACE="stdio:basic",
        EVERMIND_ARCHIVE_ROOT=str(archive_root),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
        BASIC_MEMORY_FORCE_CLOUD="true",
        BASIC_MEMORY_CLOUD_API_KEY="not-a-real-key",
        BASIC_MEMORY_CLOUD_HOST="http://127.0.0.1:9",
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from evermind_mcp.server_v2 import main_sync; main_sync()",
        ],
        env=env,
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            written = await session.call_tool(
                "write_note",
                {
                    "title": "Phase Four Local Note",
                    "content": "local-basic-memory-marker",
                    "directory": "verification",
                },
            )
            assert written.isError is False
            read = await session.call_tool(
                "read_note", {"identifier": "Phase Four Local Note"}
            )
            assert read.isError is False
            assert "local-basic-memory-marker" in read.content[0].text

    notes = list(archive_root.rglob("*.md"))
    assert any("local-basic-memory-marker" in note.read_text(encoding="utf-8") for note in notes)


@pytest.mark.asyncio
async def test_basic_memory_workspace_selector_is_a_structured_local_only_error(
    tmp_path: Path,
) -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(tmp_path / "home"),
        EVERMIND_DEFAULT_SPACE="stdio:workspace",
        EVERMIND_ARCHIVE_ROOT=str(tmp_path / "archive"),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
        BASIC_MEMORY_FORCE_CLOUD="true",
        BASIC_MEMORY_CLOUD_API_KEY="not-a-real-key",
        BASIC_MEMORY_CLOUD_HOST="http://127.0.0.1:9",
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from evermind_mcp.server_v2 import main_sync; main_sync()",
        ],
        env=env,
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(
                "create_memory_project",
                {
                    "project_name": "must-stay-local",
                    "project_path": str(tmp_path / "notes"),
                    "workspace": "team-workspace",
                },
            )

    assert result.isError is True
    assert "CLOUD_DISABLED" in result.content[0].text


@pytest.mark.asyncio
async def test_basic_memory_project_alias_resolves_through_unified_catalog(
    tmp_path: Path,
) -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    repo = tmp_path / "display-name"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    archive_root = tmp_path / "archive"
    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(tmp_path / "home"),
        EVERMIND_WORKSPACE_ROOT=str(repo),
        EVERMIND_ARCHIVE_ROOT=str(archive_root),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from evermind_mcp.server_v2 import main_sync; main_sync()",
        ],
        env=env,
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(
                "write_note",
                {
                    "title": "Unified Alias Note",
                    "content": "unified-project-alias-marker",
                    "directory": "verification",
                    "project": repo.name,
                },
            )

    assert result.isError is False
    notes = list(archive_root.rglob("*.md"))
    assert any("unified-project-alias-marker" in note.read_text(encoding="utf-8") for note in notes)


@pytest.mark.asyncio
async def test_create_memory_project_records_the_unified_catalog_binding(
    tmp_path: Path,
) -> None:
    import os
    import sqlite3

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    current = tmp_path / "current"
    current.mkdir()
    subprocess.run(["git", "init", "-q", str(current)], check=True)
    notes = tmp_path / "created-notes"
    notes.mkdir()
    home = tmp_path / "home"
    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(home),
        EVERMIND_WORKSPACE_ROOT=str(current),
        EVERMIND_ARCHIVE_ROOT=str(tmp_path / "archive"),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from evermind_mcp.server_v2 import main_sync; main_sync()",
        ],
        env=env,
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(
                "create_memory_project",
                {
                    "project_name": "Created Knowledge",
                    "project_path": str(notes),
                    "output_format": "json",
                },
            )
            assert result.isError is False

    with sqlite3.connect(home / "catalog.db") as conn:
        row = conn.execute(
            """
            SELECT binding.basic_name, binding.basic_path
            FROM basic_project_bindings binding
            JOIN projects project ON project.project_id=binding.project_id
            WHERE binding.basic_name=? AND project.state='active'
            """,
            ("Created Knowledge",),
        ).fetchone()
    assert row is not None
    assert Path(row[1]).resolve() == notes.resolve()


@pytest.mark.asyncio
async def test_real_stdio_executes_all_local_basic_memory_calls(
    tmp_path: Path,
) -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    notes = tmp_path / "compat-notes"
    notes.mkdir()
    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(tmp_path / "home"),
        EVERMIND_WORKSPACE_ROOT=str(notes),
        EVERMIND_ARCHIVE_ROOT=str(tmp_path / "archive"),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from evermind_mcp.server_v2 import main_sync; main_sync()"],
        env=env,
    )
    called: set[str] = set()

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()

            async def call(name: str, arguments: dict | None = None):
                result = await session.call_tool(name, arguments or {})
                assert result.isError is False, result.content[0].text
                called.add(name)
                structured = result.structuredContent
                assert isinstance(structured, dict)
                return structured.get("result", structured)

            project = "Compatibility Project"
            created = await call(
                "create_memory_project",
                {
                    "project_name": project,
                    "project_path": str(notes),
                    "set_default": True,
                    "output_format": "json",
                },
            )
            assert created["name"] == project

            listed = await call("list_memory_projects", {"output_format": "json"})
            assert project in json.dumps(listed)

            written = await call(
                "write_note",
                {
                    "title": "Compatibility Note",
                    "content": "initial compatibility marker",
                    "directory": "compat",
                    "project": project,
                    "output_format": "json",
                },
            )
            identifier = written["title"]
            permalink = written["permalink"]
            file_path = written["file_path"]

            read = await call(
                "read_note",
                {
                    "identifier": identifier,
                    "project": project,
                    "output_format": "json",
                },
            )
            assert "initial compatibility marker" in read["content"]

            await call(
                "edit_note",
                {
                    "identifier": identifier,
                    "operation": "append",
                    "content": "edited compatibility marker",
                    "project": project,
                    "output_format": "json",
                },
            )
            for _ in range(20):
                searched = await call(
                    "search_notes",
                    {
                        "query": "edited compatibility marker",
                        "project": project,
                        "output_format": "json",
                    },
                )
                if "edited compatibility marker" in json.dumps(searched):
                    break
                await asyncio.sleep(0.1)
            else:
                pytest.fail("edited note never reached the Basic Memory search index")

            raw = await call(
                "read_content", {"path": file_path, "project": project}
            )
            assert "edited compatibility marker" in json.dumps(raw)
            assert identifier in await call(
                "view_note", {"identifier": identifier, "project": project}
            )
            await call(
                "build_context",
                {"url": f"memory://{permalink}", "project": project},
            )
            await call(
                "recent_activity", {"project": project, "output_format": "json"}
            )
            await call("list_directory", {"project": project, "depth": 3})
            await call(
                "canvas",
                {
                    "nodes": [
                        {
                            "id": "compat",
                            "type": "text",
                            "x": 0,
                            "y": 0,
                            "width": 240,
                            "height": 120,
                            "text": "Compatibility",
                        }
                    ],
                    "edges": [],
                    "title": "Compatibility Canvas",
                    "directory": "compat",
                    "project": project,
                },
            )
            await call(
                "schema_infer",
                {"note_type": "note", "project": project, "output_format": "json"},
            )
            await call(
                "schema_diff",
                {"note_type": "note", "project": project, "output_format": "json"},
            )
            await call(
                "schema_validate",
                {"identifier": identifier, "project": project, "output_format": "json"},
            )
            await call("search", {"query": "edited compatibility marker"})
            await call("fetch", {"id": permalink})
            await call(
                "move_note",
                {
                    "identifier": identifier,
                    "destination_folder": "moved",
                    "project": project,
                    "output_format": "json",
                },
            )
            await call(
                "delete_note",
                {
                    "identifier": identifier,
                    "project": project,
                    "output_format": "json",
                },
            )
            await call("release_notes")
            detached = await call("delete_project", {"project_name": project})
            assert detached["status"] == "detached"

            after_delete = await call(
                "list_memory_projects", {"output_format": "json"}
            )
            assert project not in json.dumps(after_delete)

    assert called == {
        "build_context",
        "canvas",
        "create_memory_project",
        "delete_note",
        "delete_project",
        "edit_note",
        "fetch",
        "list_directory",
        "list_memory_projects",
        "move_note",
        "read_content",
        "read_note",
        "recent_activity",
        "release_notes",
        "schema_diff",
        "schema_infer",
        "schema_validate",
        "search",
        "search_notes",
        "view_note",
        "write_note",
    }


@pytest.mark.asyncio
async def test_unified_delete_detaches_the_only_basic_memory_project(
    tmp_path: Path,
) -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    notes = tmp_path / "only-project"
    notes.mkdir()
    config = _config(tmp_path, space="bootstrap")
    config.workspace_root = notes
    seed = MemoryService(config)
    try:
        resolved = seed.projects.resolve_workspace(notes)
        project_id = resolved["project_id"]
        seed.storage.conn.execute(
            "UPDATE projects SET state='detached' WHERE project_id='bootstrap'"
        )
        seed.storage.conn.commit()
    finally:
        seed.close()

    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(config.home),
        EVERMIND_DEFAULT_SPACE=project_id,
        EVERMIND_WORKSPACE_ROOT=str(notes),
        EVERMIND_ARCHIVE_ROOT=str(config.archive_root),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from evermind_mcp.server_v2 import main_sync; main_sync()"],
        env=env,
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            before = await session.call_tool(
                "list_memory_projects", {"output_format": "json"}
            )
            assert len(before.structuredContent["result"]["projects"]) == 1

            deleted = await session.call_tool("delete_project", {"project": project_id})
            assert deleted.isError is False, deleted.content[0].text

            after = await session.call_tool(
                "list_memory_projects", {"output_format": "json"}
            )
            assert after.structuredContent["result"]["projects"] == []

            recreated = await session.call_tool(
                "create_memory_project",
                {
                    "project_name": "Recreated Project",
                    "project_path": str(tmp_path / "recreated"),
                    "set_default": True,
                    "output_format": "json",
                },
            )
            assert recreated.isError is False, recreated.content[0].text

    assert notes.is_dir()


@pytest.mark.asyncio
async def test_local_basic_memory_ignores_cloud_credentials_without_network(
    tmp_path: Path,
) -> None:
    import os
    import socket

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.1)
    connections: list[tuple[str, int]] = []
    stopped = threading.Event()

    def accept_connections() -> None:
        while not stopped.is_set():
            try:
                connection, address = listener.accept()
            except TimeoutError:
                continue
            connections.append(address)
            connection.close()

    thread = threading.Thread(target=accept_connections, daemon=True)
    thread.start()
    port = listener.getsockname()[1]
    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(tmp_path / "home"),
        EVERMIND_DEFAULT_SPACE="stdio:no-cloud",
        EVERMIND_ARCHIVE_ROOT=str(tmp_path / "archive"),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
        BASIC_MEMORY_CLOUD_API_KEY="not-a-real-key",
        BASIC_MEMORY_CLOUD_HOST=f"http://127.0.0.1:{port}",
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from evermind_mcp.server_v2 import main_sync; main_sync()",
        ],
        env=env,
    )

    try:
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                result = await session.call_tool(
                    "list_memory_projects", {"output_format": "json"}
                )
                assert result.isError is False
    finally:
        stopped.set()
        thread.join(timeout=2)
        listener.close()

    assert connections == []


@pytest.mark.asyncio
async def test_real_stdio_ignores_poisoned_external_commands(tmp_path: Path) -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "external-command-called.txt"
    for command_name in ("codebase-memory-mcp", "basic-memory"):
        shell_script = fake_bin / command_name
        shell_script.write_text(
            f"#!/usr/bin/env sh\necho called >> '{marker.as_posix()}'\nexit 42\n",
            encoding="utf-8",
        )
        shell_script.chmod(0o755)
        (fake_bin / f"{command_name}.cmd").write_text(
            f'@echo off\r\necho called >> "{marker}"\r\nexit /b 42\r\n',
            encoding="utf-8",
        )

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def local_only():\n    return True\n", encoding="utf-8")
    env = dict(os.environ)
    env.update(
        PATH=str(fake_bin) + os.pathsep + env.get("PATH", ""),
        EVERMIND_HOME=str(tmp_path / "home"),
        EVERMIND_WORKSPACE_ROOT=str(repo),
        EVERMIND_ARCHIVE_ROOT=str(tmp_path / "archive"),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from evermind_mcp.server_v2 import main_sync; main_sync()"],
        env=env,
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            written = await session.call_tool(
                "write_note",
                {
                    "title": "Path Isolation",
                    "content": "local source only",
                    "directory": "verification",
                },
            )
            indexed = await session.call_tool(
                "index_repository", {"repo_path": str(repo)}
            )
            assert written.isError is False, written.content[0].text
            assert indexed.isError is False, indexed.content[0].text

    assert not marker.exists()


@pytest.mark.asyncio
async def test_fastmcp_core_application_errors_set_protocol_error(tmp_path: Path) -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(tmp_path / "home"),
        EVERMIND_DEFAULT_SPACE="stdio:errors",
        EVERMIND_ARCHIVE_ROOT=str(tmp_path / "archive"),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from evermind_mcp.server_v2 import main_sync; main_sync()",
        ],
        env=env,
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool("delete_project", {})

    assert result.isError is True
    assert "PROJECT_IDENTIFIER_REQUIRED" in result.content[0].text


@pytest.mark.asyncio
async def test_basic_memory_prompts_and_resources_execute_over_stdio(
    tmp_path: Path,
) -> None:
    import os

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env.update(
        EVERMIND_HOME=str(tmp_path / "home"),
        EVERMIND_DEFAULT_SPACE="stdio:resources",
        EVERMIND_ARCHIVE_ROOT=str(tmp_path / "archive"),
        BASIC_MEMORY_CONFIG_DIR=str(tmp_path / "basic-memory"),
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            "from evermind_mcp.server_v2 import main_sync; main_sync()",
        ],
        env=env,
    )

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            guide = await session.read_resource("memory://ai_assistant_guide")
            prompt = await session.get_prompt("continue_conversation", {})
            listed = await session.call_tool(
                "list_memory_projects", {"output_format": "json"}
            )
            payload = json.loads(listed.content[0].text)
            project_name = payload.get("result", payload)["projects"][0]["name"]
            info = await session.read_resource(f"memory://{project_name}/info")

    assert "Basic Memory" in guide.contents[0].text
    assert prompt.messages
    assert project_name in info.contents[0].text


@pytest.mark.asyncio
async def test_basic_memory_watcher_indexes_external_markdown_on_windows() -> None:
    if sys.platform != "win32":
        pytest.skip("8.3 short-path regression is Windows-specific")

    import os
    import tempfile

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    with tempfile.TemporaryDirectory(prefix="evermind-watch-") as temp_dir:
        root = Path(temp_dir)
        env = dict(os.environ)
        env.pop("PYTEST_CURRENT_TEST", None)
        env.update(
            EVERMIND_HOME=str(root / "home"),
            EVERMIND_DEFAULT_SPACE="stdio:watcher",
            EVERMIND_ARCHIVE_ROOT=str(root / "archive"),
            BASIC_MEMORY_CONFIG_DIR=str(root / "basic-memory"),
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-c",
                "from evermind_mcp.server_v2 import main_sync; main_sync()",
            ],
            env=env,
        )

        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                listed = await session.call_tool(
                    "list_memory_projects", {"output_format": "json"}
                )
                payload = json.loads(listed.content[0].text)
                project = payload.get("result", payload)["projects"][0]
                await asyncio.sleep(1)
                note = Path(project["path"]) / "external-watcher-note.md"
                note.write_text(
                    "---\ntitle: External Watcher Note\ntype: note\n---\n\n"
                    "external-watcher-marker",
                    encoding="utf-8",
                )

                found = False
                for _ in range(40):
                    await asyncio.sleep(0.25)
                    searched = await session.call_tool(
                        "search_notes",
                        {
                            "query": "external-watcher-marker",
                            "project": project["name"],
                            "output_format": "json",
                        },
                    )
                    result = json.loads(searched.content[0].text)
                    if result.get("result", result).get("results"):
                        found = True
                        break

        assert found is True


def test_vendored_codebase_contains_tests_and_runner_cannot_skip_missing_guards() -> (
    None
):
    source = ROOT / "third_party" / "codebase-memory-mcp"
    required = {
        "test_main.c",
        "test_incremental.c",
        "test_index_resilience.c",
        "windows/test_non_ascii_path.py",
        "windows/test_cli_non_ascii_arg.py",
    }
    present = {
        path.relative_to(source / "tests").as_posix()
        for path in (source / "tests").rglob("*")
        if path.is_file()
    }
    runner = (source / "scripts" / "test-windows.ps1").read_text(encoding="utf-8")

    assert required <= present
    assert "Test-Path -LiteralPath $t" in runner
    assert "unexpected test exit" in runner
    assert '"CC=gcc"' in runner
    assert '"CXX=g++"' in runner


def test_vendored_make_exports_selected_compiler_to_recipe_scripts() -> None:
    make = shutil.which("make")
    if not make:
        pytest.skip("GNU make is not installed")

    source = ROOT / "third_party" / "codebase-memory-mcp"
    result = subprocess.run(
        [
            make,
            "-s",
            "-f",
            "Makefile.cbm",
            '--eval=evermind-print-cc: ; @printf "%s" "$$CC"',
            "evermind-print-cc",
            "CC=gcc",
            "CXX=g++",
        ],
        cwd=source,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "gcc"


def test_vendored_rebuild_recovers_previously_crashed_file(
    tmp_path: Path, monkeypatch
) -> None:
    _set_isolated_codebase_environment(monkeypatch, tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "good.py").write_text(
        "def stable_symbol():\n    return 1\n", encoding="utf-8"
    )
    (repo / "bad.py").write_text(
        "def recovered_bad_symbol():\n    return 2\n",
        encoding="utf-8",
    )
    project = f"recovery-{tmp_path.name}"
    engine = CodebaseEngine(_vendored_config(tmp_path))
    monkeypatch.setenv("CBM_TEST_CRASH_ON", "bad.py")

    try:
        failed = engine.call(
            "index_repository",
            {"repo_path": str(repo), "project": project},
        )
        assert failed.get("skipped_count", 0) >= 1
        workspace_id = failed["workspace_id"]

        monkeypatch.delenv("CBM_TEST_CRASH_ON")
        rebuilt = engine.call(
            "index_repository",
            {"repo_path": str(repo), "project": project},
        )
        graph = engine.call(
            "search_graph",
            {"project": workspace_id, "query": "recovered_bad_symbol"},
        )
        graph_text = json.dumps(graph.get("results") or [], ensure_ascii=False)

        assert rebuilt.get("skipped_count") == 0
        assert "recovered_bad_symbol" in graph_text
    finally:
        monkeypatch.delenv("CBM_TEST_CRASH_ON", raising=False)
        if "workspace_id" in locals():
            engine.call("delete_project", {"project": workspace_id})


def test_same_name_repositories_receive_distinct_workspace_ids(
    tmp_path: Path, monkeypatch
) -> None:
    _set_isolated_codebase_environment(monkeypatch, tmp_path)
    first_repo = tmp_path / "first" / "shared"
    second_repo = tmp_path / "second" / "shared"
    first_repo.mkdir(parents=True)
    second_repo.mkdir(parents=True)
    (first_repo / "app.py").write_text(
        "def first_workspace_symbol():\n    pass\n", encoding="utf-8"
    )
    (second_repo / "app.py").write_text(
        "def second_workspace_symbol():\n    pass\n", encoding="utf-8"
    )
    engine = CodebaseEngine(_vendored_config(tmp_path))

    first = engine.call(
        "index_repository",
        {"repo_path": str(first_repo), "project": "shared-display-name"},
    )
    second = engine.call(
        "index_repository",
        {"repo_path": str(second_repo), "project": "shared-display-name"},
    )

    assert first.get("workspace_id")
    assert second.get("workspace_id")
    assert first["workspace_id"] != second["workspace_id"]
    first_graph = engine.call(
        "search_graph",
        {"project": first["workspace_id"], "query": "first_workspace_symbol"},
    )
    second_graph = engine.call(
        "search_graph",
        {"project": second["workspace_id"], "query": "second_workspace_symbol"},
    )
    assert first_graph.get("total_results", first_graph.get("total", 0)) >= 1
    assert second_graph.get("total_results", second_graph.get("total", 0)) >= 1


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason="value changes are not recognized as conflicts")
async def test_value_conflicts_are_explicitly_surfaced(tmp_path: Path) -> None:
    service = MemoryService(_config(tmp_path))
    try:
        await service.remember(
            "The deployment port is 8080", importance=1, tags=["deployment"]
        )
        conflicting = await service.remember(
            "The deployment port is 9090",
            importance=1,
            tags=["deployment"],
        )

        assert conflicting["conflicts"]
    finally:
        service.storage.close_all()


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True, reason="update mutates a row instead of superseding a version"
)
async def test_update_preserves_superseded_fact_version(tmp_path: Path) -> None:
    service = MemoryService(_config(tmp_path))
    try:
        original = await service.remember("Release channel is beta", importance=1)
        replacement = await service.update_memory(
            original["id"],
            content="Release channel is stable",
            meta={"verified": True},
        )
        columns = {
            row[1]
            for row in service.storage.conn.execute(
                "PRAGMA table_info(memories)"
            ).fetchall()
        }
        assert {"state", "supersedes_id"} <= columns
        rows = service.storage.conn.execute(
            "SELECT id, content, state, supersedes_id FROM memories "
            "WHERE content LIKE 'Release channel is %' ORDER BY created_at"
        ).fetchall()

        assert len(rows) == 2
        assert rows[0]["state"] == "superseded"
        assert rows[1]["supersedes_id"] == original["id"]
        assert replacement["id"] == rows[1]["id"]
    finally:
        service.storage.close_all()


@pytest.mark.xfail(strict=True, reason="recall has no explicit expired-history switch")
def test_recall_schema_exposes_include_expired() -> None:
    import evermind_mcp.server_v2 as server_mod

    recall = next(tool for tool in server_mod.TOOLS if tool.name == "recall")
    assert recall.inputSchema["properties"].get("include_expired") == {
        "type": "boolean",
        "default": False,
    }
