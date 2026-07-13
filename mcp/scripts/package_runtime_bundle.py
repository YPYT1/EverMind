from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import zipfile

from evermind_mcp.bundle_manifest import (
    BundleIntegrityError,
    verify_official_bundle,
)


class BundlePackageError(RuntimeError):
    """Raised when a verified runtime cannot be packaged reproducibly."""


def package_runtime_bundle(
    bundle_root: str | Path,
    output: str | Path,
    *,
    root_name: str | None = None,
) -> dict:
    bundle = Path(bundle_root).resolve()
    output_path = Path(output).resolve()
    sidecar_path = Path(f"{output_path}.sha256")
    if not bundle.is_dir():
        raise BundlePackageError(f"bundle root does not exist: {bundle}")
    if output_path.exists() or sidecar_path.exists():
        raise BundlePackageError(f"output already exists: {output_path}")
    try:
        output_path.relative_to(bundle)
    except ValueError:
        pass
    else:
        raise BundlePackageError("archive output must be outside the bundle root")

    archive_root = root_name or bundle.name
    if (
        not archive_root
        or archive_root in {".", ".."}
        or Path(archive_root).name != archive_root
        or "/" in archive_root
        or "\\" in archive_root
    ):
        raise BundlePackageError(f"invalid archive root name: {archive_root!r}")

    try:
        verified = verify_official_bundle(bundle / "app" / "evermind_mcp")
    except BundleIntegrityError as exc:
        raise BundlePackageError(str(exc)) from exc
    if verified is None:
        raise BundlePackageError("runtime bundle has no official marker")

    files = sorted(
        (path for path in bundle.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(bundle).as_posix(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    archive_temp = _temporary_path(output_path.parent, output_path.name)
    sidecar_temp = _temporary_path(output_path.parent, sidecar_path.name)
    published_archive = False
    published_sidecar = False
    try:
        with zipfile.ZipFile(
            archive_temp,
            mode="w",
            compression=zipfile.ZIP_STORED,
            allowZip64=True,
        ) as archive:
            for path in files:
                relative = path.relative_to(bundle).as_posix()
                info = zipfile.ZipInfo(
                    f"{archive_root}/{relative}",
                    date_time=(1980, 1, 1, 0, 0, 0),
                )
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                mode = stat.S_IMODE(path.stat().st_mode)
                info.external_attr = (stat.S_IFREG | mode) << 16
                with path.open("rb") as source, archive.open(
                    info, mode="w", force_zip64=True
                ) as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)

        try:
            verify_official_bundle(bundle / "app" / "evermind_mcp")
        except BundleIntegrityError as exc:
            raise BundlePackageError(
                f"bundle changed while packaging: {exc}"
            ) from exc
        digest = _sha256(archive_temp)
        sidecar_temp.write_text(
            f"{digest}  {output_path.name}\n",
            encoding="ascii",
        )
        archive_temp.replace(output_path)
        published_archive = True
        sidecar_temp.replace(sidecar_path)
        published_sidecar = True
        return {
            "archive_path": str(output_path),
            "sha256_path": str(sidecar_path),
            "sha256": digest,
            "bytes": output_path.stat().st_size,
            "file_count": len(files),
            "root_name": archive_root,
        }
    except Exception:
        for path, published in (
            (output_path, published_archive),
            (sidecar_path, published_sidecar),
            (archive_temp, False),
            (sidecar_temp, False),
        ):
            if (published or path in {archive_temp, sidecar_temp}) and path.exists():
                path.unlink()
        raise


def _temporary_path(parent: Path, name: str) -> Path:
    handle, value = tempfile.mkstemp(prefix=f".{name}-", suffix=".tmp", dir=parent)
    os.close(handle)
    return Path(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a byte-deterministic ZIP from a verified runtime bundle."
    )
    parser.add_argument("--bundle-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--root-name")
    args = parser.parse_args(argv)
    try:
        result = package_runtime_bundle(
            args.bundle_root,
            args.output,
            root_name=args.root_name,
        )
    except BundlePackageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
