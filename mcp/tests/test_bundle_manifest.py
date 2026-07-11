from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path

import pytest


REQUIRED_COMPONENT_FILES = {
    "python-runtime": "runtime/python.exe",
    "evermind": "app/evermind_mcp/__init__.py",
    "basic-memory": "app/basic_memory/__init__.py",
    "basic-memory-source": "sources/basic-memory/LICENSE",
    "codebase-engine": "bin/codebase-memory-mcp.exe",
    "embedding-model": "models/multilingual-e5-small/model.safetensors",
    "license": "licenses/AGPL-3.0-or-later.txt",
}


def _bundle_module():
    spec = importlib.util.find_spec("evermind_mcp.bundle_manifest")
    assert spec is not None, "official bundle manifest verifier is missing"
    return importlib.import_module("evermind_mcp.bundle_manifest")


def _write_manifest(package_dir: Path, manifest_path: Path, manifest: dict) -> None:
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    manifest_path.write_bytes(manifest_bytes)
    (package_dir / "_official_bundle.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "manifest": "../../evermind-runtime-manifest.json",
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def _write_bundle(tmp_path: Path) -> tuple[Path, Path, dict]:
    bundle_root = tmp_path / "EverMind"
    package_dir = bundle_root / "app" / "evermind_mcp"
    entries = []
    for component, relative in REQUIRED_COMPONENT_FILES.items():
        path = bundle_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"{component}\n".encode()
        path.write_bytes(content)
        entries.append(
            {
                "path": relative,
                "component": component,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    manifest = {
        "schema_version": 1,
        "product": "EverMind",
        "files": entries,
    }
    manifest_path = bundle_root / "evermind-runtime-manifest.json"
    _write_manifest(package_dir, manifest_path, manifest)
    return package_dir, manifest_path, manifest


def test_source_runtime_without_official_marker_is_not_blocked(tmp_path: Path) -> None:
    module = _bundle_module()

    assert module.verify_official_bundle(tmp_path / "source-package") is None


def test_complete_official_bundle_manifest_is_verified(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, manifest_path, _ = _write_bundle(tmp_path)

    result = module.verify_official_bundle(package_dir)

    assert result["manifest_path"] == str(manifest_path.resolve())
    assert result["files_verified"] == len(REQUIRED_COMPONENT_FILES)
    assert set(result["components"]) == set(REQUIRED_COMPONENT_FILES)


def test_official_bundle_root_is_discovered_from_marker(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, _, _ = _write_bundle(tmp_path)

    assert module.find_official_bundle_root(package_dir) == (
        tmp_path / "EverMind"
    ).resolve()


def test_official_bundle_verification_state_tracks_latest_result(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, _, _ = _write_bundle(tmp_path)

    assert module.is_official_bundle_verified(package_dir=package_dir) is False
    module.verify_official_bundle(package_dir)
    assert module.is_official_bundle_verified(package_dir=package_dir) is True

    model = tmp_path / "EverMind" / REQUIRED_COMPONENT_FILES["embedding-model"]
    model.write_bytes(b"X" + model.read_bytes()[1:])
    with pytest.raises(module.BundleIntegrityError):
        module.verify_official_bundle(package_dir)
    assert module.is_official_bundle_verified(package_dir=package_dir) is False


def test_official_bundle_rejects_tampered_file(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, _, _ = _write_bundle(tmp_path)
    model = tmp_path / "EverMind" / REQUIRED_COMPONENT_FILES["embedding-model"]
    original = model.read_bytes()
    model.write_bytes(b"X" + original[1:])

    with pytest.raises(module.BundleIntegrityError, match="hash mismatch"):
        module.verify_official_bundle(package_dir)


def test_official_bundle_rejects_tampered_manifest(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, manifest_path, _ = _write_bundle(tmp_path)
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")

    with pytest.raises(module.BundleIntegrityError, match="manifest hash mismatch"):
        module.verify_official_bundle(package_dir)


def test_official_bundle_marker_requires_manifest_hash(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, _, _ = _write_bundle(tmp_path)
    marker_path = package_dir / "_official_bundle.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker.pop("manifest_sha256")
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(module.BundleIntegrityError, match="manifest hash is invalid"):
        module.verify_official_bundle(package_dir)


def test_official_bundle_rejects_unmanifested_file(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, _, _ = _write_bundle(tmp_path)
    injected = package_dir / "injected.py"
    injected.write_text("raise RuntimeError('injected')\n", encoding="utf-8")

    with pytest.raises(module.BundleIntegrityError, match="unmanifested bundle files"):
        module.verify_official_bundle(package_dir)


def test_official_bundle_rejects_manifest_path_escape(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, manifest_path, manifest = _write_bundle(tmp_path)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    manifest["files"].append(
        {
            "path": "../outside.bin",
            "component": "evermind",
            "size": outside.stat().st_size,
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
        }
    )
    _write_manifest(package_dir, manifest_path, manifest)

    with pytest.raises(module.BundleIntegrityError, match="escapes bundle root"):
        module.verify_official_bundle(package_dir)


def test_official_bundle_requires_every_runtime_component(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, manifest_path, manifest = _write_bundle(tmp_path)
    manifest["files"] = [
        entry for entry in manifest["files"] if entry["component"] != "license"
    ]
    _write_manifest(package_dir, manifest_path, manifest)

    with pytest.raises(module.BundleIntegrityError, match="missing required components"):
        module.verify_official_bundle(package_dir)


def test_official_bundle_requires_basic_memory_source(tmp_path: Path) -> None:
    module = _bundle_module()
    package_dir, manifest_path, manifest = _write_bundle(tmp_path)
    manifest["files"] = [
        entry
        for entry in manifest["files"]
        if entry["component"] != "basic-memory-source"
    ]
    _write_manifest(package_dir, manifest_path, manifest)

    with pytest.raises(module.BundleIntegrityError, match="basic-memory-source"):
        module.verify_official_bundle(package_dir)


@pytest.mark.asyncio
async def test_server_verifies_official_bundle_before_starting_transport(
    monkeypatch,
) -> None:
    from evermind_mcp import server_v2

    events = []
    monkeypatch.setattr(
        server_v2,
        "verify_official_bundle",
        lambda: events.append("verified"),
        raising=False,
    )

    async def run_async(**_kwargs):
        events.append("transport")

    monkeypatch.setattr(server_v2.mcp, "run_async", run_async)

    await server_v2.main()

    assert events == ["verified", "transport"]
