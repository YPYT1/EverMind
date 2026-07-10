from __future__ import annotations

import argparse
import json
from pathlib import Path, PureWindowsPath
import shutil
import stat
import sys
import tempfile

from evermind_mcp.bundle_manifest import verify_official_bundle
from scripts.build_runtime_manifest import build_runtime_manifest


_IGNORED_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
_EDITABLE_PATHS = {
    "_editable_impl_basic_memory.pth",
    "_editable_impl_evermind_mcp.pth",
    "_virtualenv.pth",
    "_virtualenv.py",
}


class BundleStageError(RuntimeError):
    """Raised when prepared runtime inputs cannot form a complete bundle."""


def stage_runtime_bundle(
    *,
    repo_root: str | Path,
    python_runtime_root: str | Path,
    site_packages: str | Path,
    codebase_binary: str | Path,
    output: str | Path,
) -> dict:
    repo = _required_directory(repo_root, "repository root")
    runtime = _required_directory(python_runtime_root, "Python runtime root")
    packages = _required_directory(site_packages, "site-packages")
    binary = _required_file(codebase_binary, "codebase engine binary")
    output_path = Path(output).resolve()
    if output_path.exists():
        raise BundleStageError(f"output already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    python_relative = _runtime_python_relative(runtime)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_path.name}-staging-",
            dir=output_path.parent,
        )
    )
    published = False
    try:
        _copy_tree(runtime, temporary / "runtime")
        _copy_tree(
            packages,
            temporary / "app",
            ignored_names=_IGNORED_NAMES | _EDITABLE_PATHS,
        )
        _remove_absolute_path_files(temporary / "app")
        _replace_package(
            repo / "mcp" / "src" / "evermind_mcp",
            temporary / "app" / "evermind_mcp",
            "EverMind package",
        )
        _replace_package(
            repo / "third_party" / "basic-memory" / "src" / "basic_memory",
            temporary / "app" / "basic_memory",
            "Basic Memory package",
        )
        _copy_tree(
            _required_directory(
                repo / "third_party" / "basic-memory",
                "Basic Memory source",
            ),
            temporary / "sources" / "basic-memory",
        )
        _copy_codebase_notices(repo, temporary)
        binary_name = (
            "codebase-memory-mcp.exe"
            if binary.suffix.lower() == ".exe"
            else "codebase-memory-mcp"
        )
        binary_target = temporary / "bin" / binary_name
        binary_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, binary_target)
        _make_executable(binary_target)
        _copy_tree(
            _required_directory(
                repo / "third_party" / "models" / "multilingual-e5-small",
                "embedding model",
            ),
            temporary / "models" / "multilingual-e5-small",
        )
        _copy_licenses(repo, temporary)
        _write_launchers(temporary, python_relative)
        build_runtime_manifest(temporary)
        temporary.replace(output_path)
        published = True
        result = verify_official_bundle(
            output_path / "app" / "evermind_mcp"
        )
        if result is None:
            raise BundleStageError("staged bundle has no official marker")
        return result
    except Exception:
        cleanup = output_path if published else temporary
        if cleanup.exists():
            shutil.rmtree(cleanup)
        raise


def _required_directory(path: str | Path, label: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        raise BundleStageError(f"{label} does not exist: {resolved}")
    return resolved


def _required_file(path: str | Path, label: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise BundleStageError(f"{label} does not exist: {resolved}")
    return resolved


def _copy_tree(
    source: Path,
    destination: Path,
    *,
    ignored_names: set[str] = _IGNORED_NAMES,
) -> None:
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=lambda _directory, names: sorted(set(names) & ignored_names),
    )


def _replace_package(source: Path, destination: Path, label: str) -> None:
    source = _required_directory(source, label)
    if destination.exists():
        shutil.rmtree(destination)
    _copy_tree(source, destination)


def _remove_absolute_path_files(site_packages: Path) -> None:
    for path in site_packages.rglob("*.pth"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise BundleStageError(f"cannot inspect path file: {path}") from exc
        for line in lines:
            value = line.strip()
            if not value or value.startswith("#") or value.startswith("import "):
                continue
            if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
                path.unlink()
                break


def _copy_codebase_notices(repo: Path, destination: Path) -> None:
    source = _required_directory(
        repo / "third_party" / "codebase-memory-mcp",
        "codebase-memory source notices",
    )
    target = destination / "sources" / "codebase-memory-mcp"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY.md", "README.md"):
        shutil.copy2(_required_file(source / name, name), target / name)


def _copy_licenses(repo: Path, destination: Path) -> None:
    licenses = destination / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    copies = {
        repo / "LICENSE": licenses / "EverMind-AGPL-3.0-or-later.txt",
        repo / "third_party" / "basic-memory" / "LICENSE": (
            licenses / "basic-memory-AGPL-3.0-or-later.txt"
        ),
        repo / "third_party" / "codebase-memory-mcp" / "LICENSE": (
            licenses / "codebase-memory-MIT.txt"
        ),
        repo / "third_party" / "codebase-memory-mcp" / "THIRD_PARTY.md": (
            licenses / "codebase-memory-THIRD-PARTY.md"
        ),
        repo / "third_party" / "README.md": licenses / "third-party-sources.md",
        repo / "third_party" / "source-manifest.json": (
            licenses / "source-manifest.json"
        ),
        repo / "third_party" / "model-manifest.json": (
            licenses / "model-manifest.json"
        ),
    }
    for source, target in copies.items():
        shutil.copy2(_required_file(source, target.name), target)


def _runtime_python_relative(runtime: Path) -> Path:
    for relative in (
        Path("python.exe"),
        Path("bin") / "python3",
        Path("bin") / "python",
    ):
        if (runtime / relative).is_file():
            return relative
    raise BundleStageError(f"Python executable is missing from runtime: {runtime}")


def _write_launchers(bundle: Path, python_relative: Path) -> None:
    launchers = bundle / "launchers"
    launchers.mkdir(parents=True, exist_ok=True)
    bootstrap = launchers / "evermind_bootstrap.py"
    bootstrap.write_text(
        "from pathlib import Path\n"
        "import site\n\n"
        "root = Path(__file__).resolve().parents[1]\n"
        "site.addsitedir(str(root / 'app'))\n\n"
        "from evermind_mcp.server_v2 import main_sync\n\n"
        "main_sync()\n",
        encoding="utf-8",
    )
    if python_relative.name == "python.exe":
        command = (
            "@echo off\r\n"
            "setlocal\r\n"
            'set "ROOT=%~dp0.."\r\n'
            '"%ROOT%\\runtime\\python.exe" -I -B '
            '"%ROOT%\\launchers\\evermind_bootstrap.py"\r\n'
        )
        (launchers / "evermind.cmd").write_bytes(command.encode("ascii"))
        return
    launcher = launchers / "evermind"
    python_path = (Path("runtime") / python_relative).as_posix()
    launcher.write_text(
        "#!/usr/bin/env sh\n"
        'ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"\n'
        f'exec "$ROOT/{python_path}" -I -B '
        '"$ROOT/launchers/evermind_bootstrap.py"\n',
        encoding="utf-8",
    )
    _make_executable(launcher)


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage a complete EverMind runtime bundle from prepared inputs."
    )
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--python-runtime-root", required=True, type=Path)
    parser.add_argument("--site-packages", required=True, type=Path)
    parser.add_argument("--codebase-binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = stage_runtime_bundle(
            repo_root=args.repo_root,
            python_runtime_root=args.python_runtime_root,
            site_packages=args.site_packages,
            codebase_binary=args.codebase_binary,
            output=args.output,
        )
    except BundleStageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
