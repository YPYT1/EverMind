from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile


class SourceBundleError(RuntimeError):
    """Raised when tracked sources cannot be packaged reproducibly."""


def package_source_bundle(
    repo_root: str | Path,
    output: str | Path,
    *,
    root_name: str | None = None,
) -> dict:
    repo = Path(repo_root).resolve()
    output_path = Path(output).resolve()
    sidecar_path = Path(f"{output_path}.sha256")
    if not repo.is_dir():
        raise SourceBundleError(f"repository root does not exist: {repo}")
    if output_path.exists() or sidecar_path.exists():
        raise SourceBundleError(f"output already exists: {output_path}")

    archive_root = root_name or f"{repo.name}-source"
    if (
        not archive_root
        or archive_root in {".", ".."}
        or Path(archive_root).name != archive_root
        or "/" in archive_root
        or "\\" in archive_root
    ):
        raise SourceBundleError(f"invalid archive root name: {archive_root!r}")

    commit = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    files = _tracked_files(repo)
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
            for relative, mode, object_id in files:
                info = zipfile.ZipInfo(
                    f"{archive_root}/{relative}",
                    date_time=(1980, 1, 1, 0, 0, 0),
                )
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                if mode == "120000":
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, _git(repo, "cat-file", "blob", object_id))
                    continue
                permissions = 0o755 if mode == "100755" else 0o644
                info.external_attr = (stat.S_IFREG | permissions) << 16
                path = repo / Path(relative)
                try:
                    with (
                        path.open("rb") as source,
                        archive.open(info, mode="w", force_zip64=True) as destination,
                    ):
                        shutil.copyfileobj(
                            source,
                            destination,
                            length=1024 * 1024,
                        )
                except OSError as exc:
                    raise SourceBundleError(
                        f"cannot read tracked source: {relative}"
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
            "commit": commit,
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


def _tracked_files(repo: Path) -> list[tuple[str, str, str]]:
    records = _git(repo, "ls-files", "--stage", "-z").split(b"\0")
    files: list[tuple[str, str, str]] = []
    for record in records:
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise SourceBundleError("repository index contains unresolved entries")
        if mode == "160000":
            raise SourceBundleError(
                f"tracked submodule is not supported: {os.fsdecode(raw_path)}"
            )
        files.append((os.fsdecode(raw_path), mode, object_id))
    return sorted(files, key=lambda item: item[0])


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip()
        raise SourceBundleError(message or f"git {' '.join(args)} failed")
    return result.stdout


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
        description="Create a byte-deterministic ZIP from Git-tracked sources."
    )
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--root-name")
    args = parser.parse_args(argv)
    try:
        result = package_source_bundle(
            args.repo_root,
            args.output,
            root_name=args.root_name,
        )
    except SourceBundleError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
