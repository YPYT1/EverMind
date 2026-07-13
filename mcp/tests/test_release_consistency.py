from __future__ import annotations

from pathlib import Path

from scripts.check_release_consistency import (
    read_init_version,
    read_project_version,
    read_tool_count,
    run_checks,
)


def test_release_consistency_checks_pass_for_repo_state():
    assert run_checks() == []


def test_project_versions_match_repo_files():
    repo_root = Path(__file__).resolve().parents[1]
    assert read_project_version(repo_root / "pyproject.toml") == "2.0.0"
    assert (
        read_init_version(repo_root / "src" / "evermind_mcp" / "__init__.py")
        == "2.0.0"
    )


def test_server_tool_count_is_fifty():
    repo_root = Path(__file__).resolve().parents[1]
    assert read_tool_count(repo_root / "src" / "evermind_mcp" / "server_v2.py") == 50


def test_changelog_tracks_current_release_highlights():
    repo_root = Path(__file__).resolve().parents[1]
    changelog = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [2.0.0]" in changelog
    assert "50-tool unified EverMind MCP v2 interface" in changelog
    assert "Qwen/Qwen3-Embedding-8B" in changelog

