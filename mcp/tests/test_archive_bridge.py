"""Tests for the EverMind Archive candidate bridge."""
# ruff: noqa: E402

from __future__ import annotations

import json

import pytest

pytest.skip("Legacy EverOS/cloud bridge tests are not part of MCP v2.", allow_module_level=True)

from evermind_mcp.archive_bridge import ArchiveBridge
from evermind_mcp.cloud_client import EverMindMCPError


def test_propose_update_writes_candidate_only(tmp_path):
    root = tmp_path / "BasicMemory"
    candidate_dir = root / ".candidates"
    bridge = ArchiveBridge(root=str(root), candidate_dir=str(candidate_dir))

    result = bridge.propose_update(
        project_slug="coord-picker",
        target_file="修改记录.md",
        content="完成本地记忆融合。",
        evidence="tests passed",
        reason="任务完成记录",
    )

    assert result["ok"] is True
    candidate_path = candidate_dir / f"{result['candidate_id']}.json"
    assert candidate_path.exists()
    assert not (root / "projects" / "coord-picker" / "修改记录.md").exists()

    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert payload["target_file"] == "修改记录.md"


def test_commit_requires_explicit_confirmation(tmp_path):
    bridge = ArchiveBridge(root=str(tmp_path), candidate_dir=str(tmp_path / "c"))

    with pytest.raises(EverMindMCPError) as exc_info:
        bridge.commit_update(candidate_id="bm_missing", confirmed=False)

    assert exc_info.value.code == "INVALID_INPUT"


def test_commit_writes_markdown_when_target_file_missing(tmp_path):
    root = tmp_path / "BasicMemory"
    candidate_dir = root / ".candidates"
    bridge = ArchiveBridge(root=str(root), candidate_dir=str(candidate_dir))
    proposed = bridge.propose_update(
        project_slug="coord-picker",
        target_file="修改记录.md",
        content="记录内容",
        evidence="pytest",
        reason="验证候选提交",
    )

    result = bridge.commit_update(
        candidate_id=proposed["candidate_id"],
        confirmed=True,
    )

    note_file = root / "projects" / "coord-picker" / "修改记录.md"
    text = note_file.read_text(encoding="utf-8")
    assert result["ok"] is True
    assert result["action"] == "create"
    assert result["write_method"] == "direct_markdown"
    assert note_file.exists()
    assert "title: 修改记录" in text
    assert "**原因**：验证候选提交" in text
    assert "**证据**：pytest" in text
    assert "记录内容" in text


def test_commit_appends_markdown_when_target_file_exists(tmp_path):
    root = tmp_path / "BasicMemory"
    note_dir = root / "projects" / "coord-picker"
    note_dir.mkdir(parents=True)
    (note_dir / "修改记录.md").write_text("# 修改记录\n", encoding="utf-8")

    candidate_dir = root / ".candidates"
    bridge = ArchiveBridge(root=str(root), candidate_dir=str(candidate_dir))
    proposed = bridge.propose_update(
        project_slug="coord-picker",
        target_file="修改记录.md",
        content="追加内容",
        evidence="pytest",
        reason="验证追加",
    )

    result = bridge.commit_update(
        candidate_id=proposed["candidate_id"],
        confirmed=True,
    )

    text = (note_dir / "修改记录.md").read_text(encoding="utf-8")
    assert result["ok"] is True
    assert result["action"] == "append"
    assert result["write_method"] == "direct_markdown"
    assert text.startswith("# 修改记录")
    assert "**原因**：验证追加" in text
    assert "**证据**：pytest" in text
    assert "追加内容" in text




