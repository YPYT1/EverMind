from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tomllib

from scripts.package_source_bundle import package_source_bundle


REPO_ROOT = Path(__file__).resolve().parents[2]


class SourceReleaseError(RuntimeError):
    """Raised when a versioned source release cannot be produced."""


def release_source_bundle(
    *,
    repo_root: str | Path,
    output_directory: str | Path,
) -> dict:
    repo = Path(repo_root).resolve()
    output = Path(output_directory).resolve()
    version = _project_version(repo / "mcp" / "pyproject.toml")
    root_name = f"EverMind-{version}-source"
    archive = output / f"{root_name}.zip"
    output.mkdir(parents=True, exist_ok=True)
    try:
        result = package_source_bundle(
            repo,
            archive,
            root_name=root_name,
        )
    except Exception as exc:
        if isinstance(exc, SourceReleaseError):
            raise
        raise SourceReleaseError(str(exc)) from exc
    return {**result, "version": version}


def _project_version(pyproject: Path) -> str:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        version = data["project"]["version"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise SourceReleaseError(
            f"cannot read project version from {pyproject}"
        ) from exc
    if not isinstance(version, str) or not version:
        raise SourceReleaseError(f"invalid project version in {pyproject}")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Package a versioned EverMind source release."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = release_source_bundle(
            repo_root=args.repo_root,
            output_directory=args.output_directory,
        )
    except SourceReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
