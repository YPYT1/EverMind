from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from evermind_mcp.bundle_manifest import (
    BundleIntegrityError,
    OFFICIAL_BUNDLE_MARKER,
    REQUIRED_COMPONENTS,
    RUNTIME_MANIFEST_NAME,
    verify_official_bundle,
)


PACKAGE_RELATIVE = Path("app") / "evermind_mcp"


class BundleBuildError(RuntimeError):
    """Raised when a runtime staging directory cannot form an official bundle."""


def build_runtime_manifest(bundle_root: str | Path) -> dict:
    root = Path(bundle_root).resolve()
    if not root.is_dir():
        raise BundleBuildError(f"bundle root does not exist: {root}")

    package_dir = root / PACKAGE_RELATIVE
    manifest_path = root / RUNTIME_MANIFEST_NAME
    marker_path = package_dir / OFFICIAL_BUNDLE_MARKER
    excluded = {
        manifest_path.resolve(),
        marker_path.resolve(),
        manifest_path.with_suffix(manifest_path.suffix + ".tmp").resolve(),
        marker_path.with_suffix(marker_path.suffix + ".tmp").resolve(),
    }
    entries = []
    components = set()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.resolve() in excluded:
            continue
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise BundleBuildError(f"bundle file escapes root: {path}") from exc
        relative = path.relative_to(root).as_posix()
        component = _component_for_path(relative)
        components.add(component)
        entries.append(
            {
                "path": relative,
                "component": component,
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )

    missing = sorted(REQUIRED_COMPONENTS - components)
    if missing:
        raise BundleBuildError(
            f"missing required components: {', '.join(missing)}"
        )

    manifest = {
        "schema_version": 1,
        "product": "EverMind",
        "files": entries,
    }
    manifest_bytes = _json_bytes(manifest)
    marker = {
        "schema_version": 1,
        "manifest": Path(
            os.path.relpath(manifest_path, start=package_dir)
        ).as_posix(),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }

    package_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(manifest_path, manifest_bytes)
    _atomic_write(marker_path, _json_bytes(marker))
    try:
        result = verify_official_bundle(package_dir)
    except BundleIntegrityError as exc:
        raise BundleBuildError(str(exc)) from exc
    if result is None:
        raise BundleBuildError("official bundle marker was not created")
    return result


def _component_for_path(relative: str) -> str:
    if relative.startswith("runtime/"):
        return "python-runtime"
    if relative.startswith("app/evermind_mcp/"):
        return "evermind"
    if relative.startswith("app/basic_memory/"):
        return "basic-memory"
    if relative in {
        "bin/codebase-memory-mcp",
        "bin/codebase-memory-mcp.exe",
    }:
        return "codebase-engine"
    if relative.startswith("models/multilingual-e5-small/"):
        return "embedding-model"
    if relative.startswith("licenses/"):
        return "license"
    return "support"


def _json_bytes(value: dict) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate and verify an EverMind official runtime manifest."
    )
    parser.add_argument("--bundle-root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_runtime_manifest(args.bundle_root)
    except BundleBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
