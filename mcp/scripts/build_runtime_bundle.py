from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from scripts.stage_runtime_bundle import stage_runtime_bundle


REPO_ROOT = Path(__file__).resolve().parents[2]


class BundleOrchestrationError(RuntimeError):
    """Raised when the reproducible runtime environment cannot be prepared."""


def build_runtime_bundle(
    *,
    repo_root: str | Path,
    codebase_binary: str | Path,
    output: str | Path,
    python_version: str = "3.12",
    uv_executable: str = "uv",
) -> dict:
    repo = Path(repo_root).resolve()
    mcp_root = repo / "mcp"
    binary = Path(codebase_binary).resolve()
    output_path = Path(output).resolve()
    if not (mcp_root / "pyproject.toml").is_file():
        raise BundleOrchestrationError(f"MCP project is missing: {mcp_root}")
    if not binary.is_file():
        raise BundleOrchestrationError(f"codebase engine binary is missing: {binary}")

    with tempfile.TemporaryDirectory(prefix="evermind-bundle-build-") as temp:
        environment_root = Path(temp) / "venv"
        env = _clean_environment()
        env["UV_PROJECT_ENVIRONMENT"] = str(environment_root)
        try:
            _run(
                [
                    uv_executable,
                    "sync",
                    "--frozen",
                    "--no-dev",
                    "--no-editable",
                    "--managed-python",
                    "--python",
                    python_version,
                ],
                cwd=mcp_root,
                env=env,
            )
            environment_python = _environment_python(environment_root)
            info = _run(
                [
                    str(environment_python),
                    "-I",
                    "-B",
                    "-c",
                    (
                        "import json,sys,sysconfig; "
                        "print(json.dumps({'base_prefix':sys.base_prefix,"
                        "'purelib':sysconfig.get_paths()['purelib']}))"
                    ),
                ],
                cwd=mcp_root,
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise BundleOrchestrationError(detail) from exc
        try:
            paths = json.loads(info.stdout)
            runtime_root = Path(paths["base_prefix"]).resolve()
            site_packages = Path(paths["purelib"]).resolve()
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise BundleOrchestrationError(
                "prepared Python environment returned invalid path metadata"
            ) from exc
        return stage_runtime_bundle(
            repo_root=repo,
            python_runtime_root=runtime_root,
            site_packages=site_packages,
            codebase_binary=binary,
            output=output_path,
        )


def _environment_python(environment_root: Path) -> Path:
    for relative in (
        Path("Scripts") / "python.exe",
        Path("bin") / "python3",
        Path("bin") / "python",
    ):
        candidate = environment_root / relative
        if candidate.is_file():
            return candidate
    raise BundleOrchestrationError(
        f"prepared environment has no Python executable: {environment_root}"
    )


def _clean_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "UV_PROJECT_ENVIRONMENT",
        "UV_PYTHON",
        "VIRTUAL_ENV",
    ):
        env.pop(key, None)
    return env


def _run(
    args: list[str], *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a complete EverMind runtime for the current platform."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--codebase-binary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--python-version", default="3.12")
    parser.add_argument("--uv", default="uv")
    args = parser.parse_args(argv)
    try:
        result = build_runtime_bundle(
            repo_root=args.repo_root,
            codebase_binary=args.codebase_binary,
            output=args.output,
            python_version=args.python_version,
            uv_executable=args.uv,
        )
    except BundleOrchestrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
