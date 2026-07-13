from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path


def _release_module():
    spec = importlib.util.find_spec("scripts.release_source_bundle")
    assert spec is not None, "source release orchestrator is missing"
    return importlib.import_module("scripts.release_source_bundle")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "mcp").mkdir(parents=True)
    (repo / "mcp" / "pyproject.toml").write_text(
        '[project]\nname = "evermind-mcp"\nversion = "2.0.0"\n',
        encoding="utf-8",
    )
    return repo


def test_release_builds_versioned_source_archive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _release_module()
    repo = _repo(tmp_path)
    output = tmp_path / "release"
    calls = {}

    def package_source_bundle(repo_root, archive, *, root_name):
        calls["repo_root"] = Path(repo_root)
        calls["archive"] = Path(archive)
        calls["root_name"] = root_name
        Path(archive).write_bytes(b"zip")
        Path(f"{archive}.sha256").write_text("digest  archive.zip\n")
        return {"archive_path": str(archive), "sha256": "digest"}

    monkeypatch.setattr(module, "package_source_bundle", package_source_bundle)

    result = module.release_source_bundle(
        repo_root=repo,
        output_directory=output,
    )

    root_name = "EverMind-2.0.0-source"
    assert calls["repo_root"] == repo.resolve()
    assert calls["archive"] == output.resolve() / f"{root_name}.zip"
    assert calls["root_name"] == root_name
    assert result["version"] == "2.0.0"
    assert result["sha256"] == "digest"
