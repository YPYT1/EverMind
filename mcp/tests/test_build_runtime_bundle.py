from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


def _bundle_module():
    spec = importlib.util.find_spec("scripts.build_runtime_bundle")
    assert spec is not None, "runtime bundle orchestrator is missing"
    return importlib.import_module("scripts.build_runtime_bundle")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    mcp = repo / "mcp"
    mcp.mkdir(parents=True)
    (mcp / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    binary = tmp_path / "codebase-memory-mcp.exe"
    binary.write_bytes(b"binary")
    return repo, binary, tmp_path / "EverMind-runtime"


def test_orchestrator_prepares_pinned_no_dev_runtime(tmp_path: Path, monkeypatch):
    module = _bundle_module()
    repo, binary, output = _fixture(tmp_path)
    calls = []
    temporary_environment = None

    def run(args, *, cwd, env):
        nonlocal temporary_environment
        calls.append((list(args), Path(cwd), dict(env)))
        if args[1] == "sync":
            temporary_environment = Path(env["UV_PROJECT_ENVIRONMENT"])
            python = temporary_environment / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"python")
            (temporary_environment / "Lib" / "site-packages").mkdir(parents=True)
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        info = {
            "base_prefix": str(tmp_path / "managed-python"),
            "purelib": str(temporary_environment / "Lib" / "site-packages"),
        }
        return subprocess.CompletedProcess(
            args, 0, stdout=json.dumps(info), stderr=""
        )

    staged = {}

    def stage_runtime_bundle(**kwargs):
        staged.update(kwargs)
        return {"files_verified": 42}

    monkeypatch.setattr(module, "_run", run)
    monkeypatch.setattr(module, "stage_runtime_bundle", stage_runtime_bundle)

    result = module.build_runtime_bundle(
        repo_root=repo,
        codebase_binary=binary,
        output=output,
        uv_executable="uv-test",
    )

    sync = calls[0][0]
    assert sync == [
        "uv-test",
        "sync",
        "--frozen",
        "--no-dev",
        "--no-editable",
        "--managed-python",
        "--python",
        "3.12",
    ]
    assert calls[0][1] == repo / "mcp"
    assert staged == {
        "repo_root": repo.resolve(),
        "python_runtime_root": (tmp_path / "managed-python").resolve(),
        "site_packages": (
            temporary_environment / "Lib" / "site-packages"
        ).resolve(),
        "codebase_binary": binary.resolve(),
        "output": output.resolve(),
    }
    assert result == {"files_verified": 42}
    assert temporary_environment is not None
    assert not temporary_environment.exists()


def test_orchestrator_reports_uv_failure_without_staging(tmp_path: Path, monkeypatch):
    module = _bundle_module()
    repo, binary, output = _fixture(tmp_path)
    staged = False

    def fail(*_args, **_kwargs):
        raise subprocess.CalledProcessError(
            1, ["uv", "sync"], output="", stderr="sync failed"
        )

    def stage_runtime_bundle(**_kwargs):
        nonlocal staged
        staged = True

    monkeypatch.setattr(module, "_run", fail)
    monkeypatch.setattr(module, "stage_runtime_bundle", stage_runtime_bundle)

    with pytest.raises(module.BundleOrchestrationError, match="sync failed"):
        module.build_runtime_bundle(
            repo_root=repo,
            codebase_binary=binary,
            output=output,
        )

    assert staged is False
