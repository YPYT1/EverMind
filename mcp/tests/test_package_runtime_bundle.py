from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import zipfile

import pytest

from evermind_mcp.bundle_manifest import verify_official_bundle
from scripts.build_runtime_manifest import build_runtime_manifest


FILES = {
    "runtime/python.exe": b"python\n",
    "app/evermind_mcp/__init__.py": b"evermind\n",
    "app/basic_memory/__init__.py": b"basic\n",
    "sources/basic-memory/LICENSE": b"basic source\n",
    "bin/codebase-memory-mcp.exe": b"codebase\n",
    "models/multilingual-e5-small/model.safetensors": b"model\n",
    "licenses/AGPL.txt": b"license\n",
    "launchers/evermind.cmd": b"launcher\n",
}


def _package_module():
    spec = importlib.util.find_spec("scripts.package_runtime_bundle")
    assert spec is not None, "runtime bundle packager is missing"
    return importlib.import_module("scripts.package_runtime_bundle")


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "staging" / "EverMind-runtime"
    for relative, content in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    build_runtime_manifest(root)
    return root


def test_runtime_zip_is_byte_deterministic_and_verifiable(tmp_path: Path) -> None:
    module = _package_module()
    bundle = _bundle(tmp_path)
    root_name = "EverMind-2.0.0-windows-x86_64"
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    first_result = module.package_runtime_bundle(
        bundle, first, root_name=root_name
    )
    second_result = module.package_runtime_bundle(
        bundle, second, root_name=root_name
    )

    assert first.read_bytes() == second.read_bytes()
    assert first_result["sha256"] == second_result["sha256"]
    assert first_result["file_count"] == len(FILES) + 2
    assert (tmp_path / "first.zip.sha256").read_text(encoding="ascii").endswith(
        "  first.zip\n"
    )
    with zipfile.ZipFile(first) as archive:
        infos = archive.infolist()
        assert [info.filename for info in infos] == sorted(
            f"{root_name}/{relative}"
            for relative in [
                *FILES,
                "app/evermind_mcp/_official_bundle.json",
                "evermind-runtime-manifest.json",
            ]
        )
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
        assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(first) as archive:
        archive.extractall(extracted)
    verified = verify_official_bundle(
        extracted / root_name / "app" / "evermind_mcp"
    )
    assert verified is not None


def test_runtime_packager_refuses_existing_output(tmp_path: Path) -> None:
    module = _package_module()
    bundle = _bundle(tmp_path)
    output = tmp_path / "release.zip"
    output.write_bytes(b"keep")

    with pytest.raises(module.BundlePackageError, match="output already exists"):
        module.package_runtime_bundle(bundle, output)

    assert output.read_bytes() == b"keep"


def test_runtime_packager_rejects_unsafe_archive_root(tmp_path: Path) -> None:
    module = _package_module()
    bundle = _bundle(tmp_path)

    with pytest.raises(module.BundlePackageError, match="archive root name"):
        module.package_runtime_bundle(
            bundle,
            tmp_path / "release.zip",
            root_name="../escape",
        )
