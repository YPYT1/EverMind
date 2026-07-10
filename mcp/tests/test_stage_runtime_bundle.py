from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

from evermind_mcp.bundle_manifest import verify_official_bundle


def _stage_module():
    spec = importlib.util.find_spec("scripts.stage_runtime_bundle")
    assert spec is not None, "runtime bundle staging script is missing"
    return importlib.import_module("scripts.stage_runtime_bundle")


def _write(path: Path, content: bytes = b"fixture\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _fixture(tmp_path: Path) -> dict[str, Path]:
    repo = tmp_path / "repo"
    runtime = tmp_path / "python-runtime"
    site_packages = tmp_path / "site-packages"
    binary = repo / "third_party" / "codebase-memory-mcp" / "build" / "c" / "codebase-memory-mcp.exe"

    _write(repo / "mcp" / "src" / "evermind_mcp" / "__init__.py")
    _write(
        repo
        / "third_party"
        / "basic-memory"
        / "src"
        / "basic_memory"
        / "__init__.py"
    )
    _write(repo / "third_party" / "basic-memory" / "LICENSE")
    _write(repo / "third_party" / "basic-memory" / "pyproject.toml")
    _write(repo / "third_party" / "codebase-memory-mcp" / "LICENSE")
    _write(repo / "third_party" / "codebase-memory-mcp" / "THIRD_PARTY.md")
    _write(repo / "third_party" / "codebase-memory-mcp" / "README.md")
    _write(
        repo
        / "third_party"
        / "models"
        / "multilingual-e5-small"
        / "model.safetensors"
    )
    _write(
        repo / "third_party" / "models" / "multilingual-e5-small" / "config.json"
    )
    _write(repo / "third_party" / "source-manifest.json")
    _write(repo / "third_party" / "model-manifest.json")
    _write(repo / "third_party" / "README.md")
    _write(repo / "LICENSE")
    _write(binary)
    _write(runtime / "python.exe")
    _write(runtime / "Lib" / "os.py")
    _write(site_packages / "dependency.py")
    _write(site_packages / "relative-paths.pth", b"win32\n")
    _write(site_packages / "_virtualenv.pth", b"import _virtualenv\n")
    _write(site_packages / "_virtualenv.py")
    _write(
        site_packages / "absolute-source.pth",
        str(repo / "external-source").encode(),
    )
    _write(
        site_packages / "_editable_impl_evermind_mcp.pth",
        str(repo / "mcp" / "src").encode(),
    )
    _write(
        site_packages / "_editable_impl_basic_memory.pth",
        str(repo / "third_party" / "basic-memory" / "src").encode(),
    )
    return {
        "repo": repo,
        "runtime": runtime,
        "site_packages": site_packages,
        "binary": binary,
        "output": tmp_path / "EverMind-runtime",
    }


def test_stage_runtime_bundle_creates_complete_verified_layout(tmp_path: Path) -> None:
    module = _stage_module()
    paths = _fixture(tmp_path)

    result = module.stage_runtime_bundle(
        repo_root=paths["repo"],
        python_runtime_root=paths["runtime"],
        site_packages=paths["site_packages"],
        codebase_binary=paths["binary"],
        output=paths["output"],
    )

    output = paths["output"]
    package = output / "app" / "evermind_mcp"
    assert result == verify_official_bundle(package)
    for relative in (
        "runtime/python.exe",
        "app/dependency.py",
        "app/relative-paths.pth",
        "app/evermind_mcp/__init__.py",
        "app/basic_memory/__init__.py",
        "sources/basic-memory/src/basic_memory/__init__.py",
        "sources/codebase-memory-mcp/LICENSE",
        "bin/codebase-memory-mcp.exe",
        "models/multilingual-e5-small/model.safetensors",
        "licenses/EverMind-AGPL-3.0-or-later.txt",
        "licenses/basic-memory-AGPL-3.0-or-later.txt",
        "licenses/codebase-memory-MIT.txt",
        "licenses/source-manifest.json",
        "licenses/model-manifest.json",
        "launchers/evermind_bootstrap.py",
        "launchers/evermind.cmd",
        "evermind-runtime-manifest.json",
    ):
        assert (output / relative).is_file(), relative
    assert not (output / "app" / "_editable_impl_evermind_mcp.pth").exists()
    assert not (output / "app" / "_editable_impl_basic_memory.pth").exists()
    assert not (output / "app" / "_virtualenv.pth").exists()
    assert not (output / "app" / "_virtualenv.py").exists()
    assert not (output / "app" / "absolute-source.pth").exists()
    assert "site.addsitedir" in (
        output / "launchers" / "evermind_bootstrap.py"
    ).read_text(encoding="utf-8")
    launcher = (output / "launchers" / "evermind.cmd").read_text(encoding="ascii")
    assert " -I -B " in launcher


def test_stage_runtime_bundle_refuses_existing_output(tmp_path: Path) -> None:
    module = _stage_module()
    paths = _fixture(tmp_path)
    paths["output"].mkdir()
    sentinel = paths["output"] / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(module.BundleStageError, match="output already exists"):
        module.stage_runtime_bundle(
            repo_root=paths["repo"],
            python_runtime_root=paths["runtime"],
            site_packages=paths["site_packages"],
            codebase_binary=paths["binary"],
            output=paths["output"],
        )

    assert sentinel.read_text(encoding="utf-8") == "keep"
