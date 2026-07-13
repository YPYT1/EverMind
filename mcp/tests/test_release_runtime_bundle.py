from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest


def _release_module():
    spec = importlib.util.find_spec("scripts.release_runtime_bundle")
    assert spec is not None, "runtime release orchestrator is missing"
    return importlib.import_module("scripts.release_runtime_bundle")


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    (repo / "mcp").mkdir(parents=True)
    (repo / "mcp" / "pyproject.toml").write_text(
        '[project]\nname = "evermind-mcp"\nversion = "2.0.0"\n',
        encoding="utf-8",
    )
    binary = tmp_path / "codebase-memory-mcp.exe"
    binary.write_bytes(b"binary")
    return repo, binary


@pytest.mark.parametrize(
    ("system", "machine", "tag"),
    [
        ("Windows", "AMD64", "windows-x86_64"),
        ("Windows", "ARM64", "windows-aarch64"),
        ("Darwin", "x86_64", "macos-x86_64"),
        ("Darwin", "arm64", "macos-aarch64"),
        ("Linux", "x86_64", "linux-x86_64"),
        ("Linux", "aarch64", "linux-aarch64"),
    ],
)
def test_platform_tag_normalizes_supported_targets(system, machine, tag):
    module = _release_module()

    assert module.platform_tag(system, machine) == tag


def test_release_builds_named_runtime_archive_and_cleans_staging(
    tmp_path: Path, monkeypatch
) -> None:
    module = _release_module()
    repo, binary = _repo(tmp_path)
    output = tmp_path / "release"
    calls = {}

    def build_runtime_bundle(**kwargs):
        calls["build"] = kwargs
        Path(kwargs["output"]).mkdir(parents=True)
        return {"files_verified": 42}

    def package_runtime_bundle(bundle_root, archive, *, root_name):
        calls["package"] = {
            "bundle_root": Path(bundle_root),
            "archive": Path(archive),
            "root_name": root_name,
        }
        Path(archive).write_bytes(b"zip")
        Path(f"{archive}.sha256").write_text("digest  archive.zip\n")
        return {"archive_path": str(archive), "sha256": "digest"}

    monkeypatch.setattr(module, "build_runtime_bundle", build_runtime_bundle)
    monkeypatch.setattr(module, "package_runtime_bundle", package_runtime_bundle)

    result = module.release_runtime_bundle(
        repo_root=repo,
        codebase_binary=binary,
        output_directory=output,
        target_tag="windows-x86_64",
    )

    root_name = "EverMind-2.0.0-windows-x86_64"
    assert calls["build"]["repo_root"] == repo.resolve()
    assert calls["build"]["codebase_binary"] == binary.resolve()
    assert calls["package"]["root_name"] == root_name
    assert calls["package"]["archive"] == output.resolve() / f"{root_name}.zip"
    assert result["version"] == "2.0.0"
    assert result["target"] == "windows-x86_64"
    assert result["files_verified"] == 42
    assert not calls["package"]["bundle_root"].exists()


def test_release_refuses_existing_artifacts_before_building(
    tmp_path: Path, monkeypatch
) -> None:
    module = _release_module()
    repo, binary = _repo(tmp_path)
    output = tmp_path / "release"
    output.mkdir()
    archive = output / "EverMind-2.0.0-windows-x86_64.zip"
    archive.write_bytes(b"keep")
    built = False

    def build_runtime_bundle(**_kwargs):
        nonlocal built
        built = True

    monkeypatch.setattr(module, "build_runtime_bundle", build_runtime_bundle)

    with pytest.raises(module.RuntimeReleaseError, match="already exists"):
        module.release_runtime_bundle(
            repo_root=repo,
            codebase_binary=binary,
            output_directory=output,
            target_tag="windows-x86_64",
        )

    assert archive.read_bytes() == b"keep"
    assert built is False
