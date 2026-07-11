from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import subprocess
import zipfile


def _source_package_module():
    spec = importlib.util.find_spec("scripts.package_source_bundle")
    assert spec is not None, "source bundle packager is missing"
    return importlib.import_module("scripts.package_source_bundle")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    files = {
        "LICENSE": "AGPL\n",
        "mcp/src/evermind_mcp/__init__.py": "VERSION = 'test'\n",
        "scripts/build.sh": "#!/bin/sh\n",
        "third_party/basic-memory/tests/test_local.py": "def test_local(): pass\n",
        "third_party/codebase-memory-mcp/tests/fixtures/sample.txt": "fixture\n",
    }
    for relative, content in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "init")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=EverMind Tests",
        "-c",
        "user.email=tests@evermind.local",
        "commit",
        "-m",
        "initial",
    )
    (repo / "untracked.txt").write_text("exclude me\n", encoding="utf-8")
    return repo


def test_source_zip_is_byte_deterministic_and_contains_tracked_sources(
    tmp_path: Path,
) -> None:
    module = _source_package_module()
    repo = _repo(tmp_path)
    root_name = "EverMind-2.0.0-source"
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    first_result = module.package_source_bundle(
        repo,
        first,
        root_name=root_name,
    )
    second_result = module.package_source_bundle(
        repo,
        second,
        root_name=root_name,
    )

    tracked = _git(repo, "ls-files").splitlines()
    expected = sorted(f"{root_name}/{relative}" for relative in tracked)
    assert first.read_bytes() == second.read_bytes()
    assert first_result["sha256"] == second_result["sha256"]
    assert first_result["commit"] == _git(repo, "rev-parse", "HEAD")
    assert first_result["file_count"] == len(tracked)
    assert (
        (tmp_path / "first.zip.sha256")
        .read_text(encoding="ascii")
        .endswith("  first.zip\n")
    )
    with zipfile.ZipFile(first) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == expected
        assert f"{root_name}/untracked.txt" not in archive.namelist()
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
        assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)
