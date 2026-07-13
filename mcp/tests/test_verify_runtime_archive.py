from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import zipfile

import pytest


def _verify_module():
    spec = importlib.util.find_spec("scripts.verify_runtime_archive")
    assert spec is not None, "runtime archive verifier is missing"
    return importlib.import_module("scripts.verify_runtime_archive")


def _archive(tmp_path: Path, roots: tuple[str, ...] = ("EverMind-runtime",)) -> Path:
    archive = tmp_path / "runtime.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for root in roots:
            bundle.writestr(f"{root}/launchers/evermind.cmd", b"launcher\n")
    return archive


def test_runtime_archive_verifier_extracts_one_root_and_runs_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _verify_module()
    archive = _archive(tmp_path)
    observed = {}

    async def verify_server(bundle_root: Path, state_root: Path, timeout: float):
        observed["bundle_root"] = bundle_root
        observed["state_root"] = state_root
        observed["timeout"] = timeout
        assert (bundle_root / "launchers" / "evermind.cmd").is_file()
        return {"tool_count": 50}

    monkeypatch.setattr(module, "_verify_server", verify_server)

    result = module.verify_runtime_archive(archive, timeout=12.5)

    assert result == {"tool_count": 50}
    assert observed["bundle_root"].name == "EverMind-runtime"
    assert observed["state_root"].parent == observed["bundle_root"].parent
    assert observed["timeout"] == 12.5


def test_runtime_archive_verifier_rejects_multiple_roots(tmp_path: Path) -> None:
    module = _verify_module()
    archive = _archive(tmp_path, roots=("first", "second"))

    with pytest.raises(module.RuntimeArchiveError, match="one root directory"):
        module.verify_runtime_archive(archive)


def test_runtime_archive_directory_requires_exactly_one_zip(tmp_path: Path) -> None:
    module = _verify_module()

    with pytest.raises(module.RuntimeArchiveError, match="exactly one runtime ZIP"):
        module.find_runtime_archive(tmp_path)

    archive = _archive(tmp_path)
    assert module.find_runtime_archive(tmp_path) == archive.resolve()

    (tmp_path / "second.zip").write_bytes(b"zip")
    with pytest.raises(module.RuntimeArchiveError, match="exactly one runtime ZIP"):
        module.find_runtime_archive(tmp_path)
