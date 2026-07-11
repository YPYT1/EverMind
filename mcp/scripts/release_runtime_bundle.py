from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib

from scripts.build_runtime_bundle import build_runtime_bundle
from scripts.package_runtime_bundle import package_runtime_bundle


REPO_ROOT = Path(__file__).resolve().parents[2]


class RuntimeReleaseError(RuntimeError):
    """Raised when a complete platform runtime release cannot be produced."""


def platform_tag(system: str | None = None, machine: str | None = None) -> str:
    system_name = (system or platform.system()).strip().lower()
    machine_name = (machine or platform.machine()).strip().lower()
    systems = {"windows": "windows", "darwin": "macos", "linux": "linux"}
    machines = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }
    try:
        return f"{systems[system_name]}-{machines[machine_name]}"
    except KeyError as exc:
        raise RuntimeReleaseError(
            f"unsupported runtime target: {system_name}-{machine_name}"
        ) from exc


def release_runtime_bundle(
    *,
    repo_root: str | Path,
    codebase_binary: str | Path,
    output_directory: str | Path,
    target_tag: str | None = None,
    python_version: str = "3.12",
    uv_executable: str = "uv",
) -> dict:
    repo = Path(repo_root).resolve()
    binary = Path(codebase_binary).resolve()
    output = Path(output_directory).resolve()
    version = _project_version(repo / "mcp" / "pyproject.toml")
    target = target_tag or platform_tag()
    root_name = f"EverMind-{version}-{target}"
    archive = output / f"{root_name}.zip"
    sidecar = Path(f"{archive}.sha256")
    if archive.exists() or sidecar.exists():
        raise RuntimeReleaseError(f"release artifact already exists: {archive}")
    output.mkdir(parents=True, exist_ok=True)

    staging = Path(
        tempfile.mkdtemp(prefix=f".{root_name}-staging-", dir=output)
    ) / root_name
    try:
        build_result = build_runtime_bundle(
            repo_root=repo,
            codebase_binary=binary,
            output=staging,
            python_version=python_version,
            uv_executable=uv_executable,
        )
        package_result = package_runtime_bundle(
            staging,
            archive,
            root_name=root_name,
        )
    except Exception as exc:
        if isinstance(exc, RuntimeReleaseError):
            raise
        raise RuntimeReleaseError(str(exc)) from exc
    finally:
        staging_parent = staging.parent
        if staging_parent.exists():
            shutil.rmtree(staging_parent)
    return {
        **package_result,
        "version": version,
        "target": target,
        "files_verified": build_result["files_verified"],
    }


def _project_version(pyproject: Path) -> str:
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        version = data["project"]["version"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeReleaseError(
            f"cannot read project version from {pyproject}"
        ) from exc
    if not isinstance(version, str) or not version:
        raise RuntimeReleaseError(f"invalid project version in {pyproject}")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build and package a complete EverMind platform runtime."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--codebase-binary", required=True, type=Path)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--target")
    parser.add_argument("--python-version", default="3.12")
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args(argv)
    try:
        result = release_runtime_bundle(
            repo_root=args.repo_root,
            codebase_binary=args.codebase_binary,
            output_directory=args.output_directory,
            target_tag=args.target,
            python_version=args.python_version,
            uv_executable=args.uv,
        )
    except RuntimeReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
