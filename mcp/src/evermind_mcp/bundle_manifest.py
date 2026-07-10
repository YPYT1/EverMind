"""Integrity verification for official EverMind runtime bundles."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


OFFICIAL_BUNDLE_MARKER = "_official_bundle.json"
RUNTIME_MANIFEST_NAME = "evermind-runtime-manifest.json"
REQUIRED_COMPONENTS = frozenset(
    {
        "python-runtime",
        "evermind",
        "basic-memory",
        "codebase-engine",
        "embedding-model",
        "license",
    }
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class BundleIntegrityError(RuntimeError):
    """Raised when an official runtime bundle is incomplete or modified."""


def verify_official_bundle(package_dir: str | Path | None = None) -> dict | None:
    """Verify the official bundle containing ``package_dir`` when marked."""
    package = Path(package_dir) if package_dir is not None else Path(__file__).parent
    marker_path = package / OFFICIAL_BUNDLE_MARKER
    if not marker_path.is_file():
        return None

    marker = _read_json(marker_path, "official bundle marker")
    if marker.get("schema_version") != 1:
        raise BundleIntegrityError("unsupported official bundle marker schema")
    manifest_reference = marker.get("manifest")
    if not isinstance(manifest_reference, str) or not manifest_reference:
        raise BundleIntegrityError("official bundle marker has no manifest path")
    if Path(manifest_reference).is_absolute():
        raise BundleIntegrityError("official bundle manifest path must be relative")

    manifest_path = (package / manifest_reference).resolve()
    if manifest_path.name != RUNTIME_MANIFEST_NAME:
        raise BundleIntegrityError(
            f"official bundle manifest must be named {RUNTIME_MANIFEST_NAME}"
        )
    bundle_root = manifest_path.parent
    try:
        package.resolve().relative_to(bundle_root)
    except ValueError as exc:
        raise BundleIntegrityError(
            "official bundle manifest does not contain the package"
        ) from exc

    manifest = _read_json(manifest_path, "runtime manifest")
    if manifest.get("schema_version") != 1 or manifest.get("product") != "EverMind":
        raise BundleIntegrityError("unsupported EverMind runtime manifest")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise BundleIntegrityError("runtime manifest has no files")

    components: set[str] = set()
    verified_paths: set[Path] = set()
    for entry in files:
        path, component, expected_size, expected_hash = _validate_entry(entry)
        resolved = (bundle_root / path).resolve()
        try:
            resolved.relative_to(bundle_root)
        except ValueError as exc:
            raise BundleIntegrityError(
                f"manifest path escapes bundle root: {path}"
            ) from exc
        if resolved in verified_paths:
            raise BundleIntegrityError(f"duplicate manifest path: {path}")
        verified_paths.add(resolved)
        components.add(component)
        if not resolved.is_file():
            raise BundleIntegrityError(f"bundle file is missing: {path}")
        if resolved.stat().st_size != expected_size:
            raise BundleIntegrityError(f"bundle file size mismatch: {path}")
        if _sha256(resolved) != expected_hash:
            raise BundleIntegrityError(f"bundle file hash mismatch: {path}")

    missing = sorted(REQUIRED_COMPONENTS - components)
    if missing:
        raise BundleIntegrityError(
            f"missing required components: {', '.join(missing)}"
        )
    return {
        "manifest_path": str(manifest_path),
        "files_verified": len(verified_paths),
        "components": sorted(components),
    }


def _read_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleIntegrityError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise BundleIntegrityError(f"{label} must be a JSON object")
    return value


def _validate_entry(entry: object) -> tuple[str, str, int, str]:
    if not isinstance(entry, dict):
        raise BundleIntegrityError("runtime manifest file entry must be an object")
    path = entry.get("path")
    component = entry.get("component")
    size = entry.get("size")
    digest = entry.get("sha256")
    if not isinstance(path, str) or not path or Path(path).is_absolute():
        raise BundleIntegrityError("runtime manifest file path must be relative")
    if not isinstance(component, str) or not component:
        raise BundleIntegrityError(f"runtime manifest component is missing: {path}")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise BundleIntegrityError(f"runtime manifest size is invalid: {path}")
    if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
        raise BundleIntegrityError(f"runtime manifest hash is invalid: {path}")
    return path, component, size, digest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
