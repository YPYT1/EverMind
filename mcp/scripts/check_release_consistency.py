from __future__ import annotations

import asyncio
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
INIT_PATH = REPO_ROOT / "src" / "evermind_mcp" / "__init__.py"
SERVER_PATH = REPO_ROOT / "src" / "evermind_mcp" / "server_v2.py"
EXPECTED_TOOL_COUNT = 50


def read_project_version(pyproject_path: Path = PYPROJECT_PATH) -> str:
    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError(f"Could not parse version from {pyproject_path}")
    return match.group(1)


def read_init_version(init_path: Path = INIT_PATH) -> str:
    content = init_path.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if not match:
        raise ValueError(f"Could not parse __version__ from {init_path}")
    return match.group(1)


def read_tool_count(server_path: Path = SERVER_PATH) -> int:
    import importlib.util
    import sys

    src_root = server_path.parents[2]
    sys.path.insert(0, str(src_root))
    try:
        spec = importlib.util.spec_from_file_location(
            "evermind_mcp.server_v2",
            server_path,
        )
        if spec is None or spec.loader is None:
            raise ValueError(f"Could not import {server_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["evermind_mcp.server_v2"] = module
        spec.loader.exec_module(module)
        return len(asyncio.run(module.mcp.list_tools()))
    finally:
        try:
            sys.path.remove(str(src_root))
        except ValueError:
            pass


def run_checks() -> list[str]:
    errors: list[str] = []
    version = read_project_version()
    init_version = read_init_version()
    if version != init_version:
        errors.append(
            f"Version mismatch: pyproject.toml has {version}, __init__.py has {init_version}"
        )

    tool_count = read_tool_count()
    if tool_count != EXPECTED_TOOL_COUNT:
        errors.append(
            f"Tool count mismatch: FastMCP exposes {tool_count}, expected {EXPECTED_TOOL_COUNT}"
        )

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for required in ["EverMind MCP", "evermind-mcp", "50 tools"]:
        if required not in readme:
            errors.append(f"Missing '{required}' in README.md")
    for forbidden in ["tt-a1i", "uvx evermind-mcp@latest"]:
        if forbidden in readme:
            errors.append(f"Forbidden '{forbidden}' found in README.md")

    return errors


def main() -> int:
    errors = run_checks()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Release consistency checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
