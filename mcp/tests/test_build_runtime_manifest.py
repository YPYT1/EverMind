from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from evermind_mcp.bundle_manifest import verify_official_bundle


STAGING_FILES = {
    "runtime/python.exe": b"python-runtime\n",
    "app/evermind_mcp/__init__.py": b"evermind\n",
    "app/basic_memory/__init__.py": b"basic-memory\n",
    "bin/codebase-memory-mcp.exe": b"codebase-engine\n",
    "models/multilingual-e5-small/model.safetensors": b"embedding-model\n",
    "licenses/AGPL-3.0-or-later.txt": b"license\n",
    "launchers/evermind.cmd": b"launcher\n",
}


def _builder_module():
    spec = importlib.util.find_spec("scripts.build_runtime_manifest")
    assert spec is not None, "runtime manifest builder is missing"
    return importlib.import_module("scripts.build_runtime_manifest")


def _write_staging(tmp_path: Path) -> Path:
    root = tmp_path / "EverMind"
    for relative, content in STAGING_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return root


def test_builder_generates_manifest_that_runtime_verifies(tmp_path: Path) -> None:
    module = _builder_module()
    root = _write_staging(tmp_path)

    result = module.build_runtime_manifest(root)

    package_dir = root / "app" / "evermind_mcp"
    verified = verify_official_bundle(package_dir)
    manifest_path = root / "evermind-runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [entry["path"] for entry in manifest["files"]]
    marker = json.loads(
        (package_dir / "_official_bundle.json").read_text(encoding="utf-8")
    )

    assert result == verified
    assert paths == sorted(STAGING_FILES)
    assert paths == sorted(paths)
    assert next(
        entry for entry in manifest["files"] if entry["path"].startswith("launchers/")
    )["component"] == "support"
    assert marker["manifest_sha256"] == hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()


def test_builder_output_is_byte_deterministic(tmp_path: Path) -> None:
    module = _builder_module()
    root = _write_staging(tmp_path)
    manifest_path = root / "evermind-runtime-manifest.json"
    marker_path = root / "app" / "evermind_mcp" / "_official_bundle.json"

    module.build_runtime_manifest(root)
    first = (manifest_path.read_bytes(), marker_path.read_bytes())
    module.build_runtime_manifest(root)

    assert (manifest_path.read_bytes(), marker_path.read_bytes()) == first


def test_builder_refuses_incomplete_staging_without_writing_marker(
    tmp_path: Path,
) -> None:
    module = _builder_module()
    root = _write_staging(tmp_path)
    (root / "models" / "multilingual-e5-small" / "model.safetensors").unlink()

    with pytest.raises(module.BundleBuildError, match="missing required components"):
        module.build_runtime_manifest(root)

    assert not (root / "evermind-runtime-manifest.json").exists()
    assert not (root / "app" / "evermind_mcp" / "_official_bundle.json").exists()


def test_builder_cli_reports_verification_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _builder_module()
    root = _write_staging(tmp_path)

    exit_code = module.main(["--bundle-root", str(root)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["files_verified"] == len(STAGING_FILES)
