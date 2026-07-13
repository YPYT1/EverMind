from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import zipfile


class RuntimeArchiveError(RuntimeError):
    """Raised when a packaged runtime cannot start as the complete local MCP."""


def find_runtime_archive(directory: str | Path) -> Path:
    root = Path(directory).resolve()
    archives = sorted(root.glob("*.zip")) if root.is_dir() else []
    if len(archives) != 1:
        raise RuntimeArchiveError(
            f"expected exactly one runtime ZIP in {root}, found {len(archives)}"
        )
    return archives[0].resolve()


def verify_runtime_archive(
    archive: str | Path,
    *,
    timeout: float = 180.0,
) -> dict:
    archive_path = Path(archive).resolve()
    if not archive_path.is_file():
        raise RuntimeArchiveError(f"runtime ZIP does not exist: {archive_path}")

    with tempfile.TemporaryDirectory(prefix="evermind-runtime-smoke-") as temporary:
        destination = Path(temporary)
        with zipfile.ZipFile(archive_path) as bundle:
            bad = bundle.testzip()
            if bad is not None:
                raise RuntimeArchiveError(f"runtime ZIP CRC failed: {bad}")
            roots = _archive_roots(bundle)
            if len(roots) != 1:
                raise RuntimeArchiveError(
                    f"runtime ZIP must contain one root directory, found {roots}"
                )
            bundle.extractall(destination)

        bundle_root = destination / roots[0]
        state_root = destination / "state"
        try:
            return asyncio.run(_verify_server(bundle_root, state_root, timeout))
        except RuntimeArchiveError:
            raise
        except TimeoutError as exc:
            raise RuntimeArchiveError(
                f"bundled MCP did not complete verification within {timeout:g}s"
            ) from exc
        except Exception as exc:
            raise RuntimeArchiveError(f"bundled MCP verification failed: {exc}") from exc


def _archive_roots(bundle: zipfile.ZipFile) -> list[str]:
    roots: set[str] = set()
    for info in bundle.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise RuntimeArchiveError(f"unsafe runtime ZIP path: {info.filename}")
        roots.add(path.parts[0])
    return sorted(roots)


async def _verify_server(
    bundle_root: Path,
    state_root: Path,
    timeout: float,
) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    state_root.mkdir(parents=True, exist_ok=True)
    command, args = _launcher_command(bundle_root)
    env = dict(os.environ)
    for key in (
        "EVERMIND_SILICONFLOW_API_KEY",
        "SILICONFLOW_API_KEY",
        "EVERMIND_EMBED_API_KEY",
        "EVERMIND_LLM_API_KEY",
    ):
        env.pop(key, None)
    env.update(
        EVERMIND_HOME=str(state_root / "evermind"),
        EVERMIND_DEFAULT_SPACE="runtime:smoke",
        EVERMIND_ARCHIVE_ROOT=str(state_root / "archive"),
        BASIC_MEMORY_CONFIG_DIR=str(state_root / "basic-memory"),
        HOME=str(state_root / "home"),
        USERPROFILE=str(state_root / "home"),
        LOCALAPPDATA=str(state_root / "localappdata"),
        APPDATA=str(state_root / "appdata"),
    )
    params = StdioServerParameters(command=command, args=args, env=env)

    async with asyncio.timeout(timeout):
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                counts = {
                    "tool_count": len((await session.list_tools()).tools),
                    "prompt_count": len((await session.list_prompts()).prompts),
                    "resource_count": len((await session.list_resources()).resources),
                    "resource_template_count": len(
                        (await session.list_resource_templates()).resourceTemplates
                    ),
                }
                expected_counts = {
                    "tool_count": 50,
                    "prompt_count": 3,
                    "resource_count": 1,
                    "resource_template_count": 1,
                }
                if counts != expected_counts:
                    raise RuntimeArchiveError(
                        f"bundled MCP surface mismatch: {counts}"
                    )

                status_result = await session.call_tool("status", {})
                if status_result.isError:
                    raise RuntimeArchiveError(
                        f"bundled MCP status failed: {status_result.content}"
                    )
                status = _tool_payload(status_result)
                expected_status = {
                    "embedding_available": True,
                    "codebase_backend": "vendored-codebase-memory-mcp",
                    "codebase_source_integrated": True,
                    "codebase_binary_available": True,
                    "archive_backend": "source-fused-basic-memory",
                    "archive_source_integrated": True,
                }
                mismatches = {
                    key: {"expected": expected, "actual": status.get(key)}
                    for key, expected in expected_status.items()
                    if status.get(key) != expected
                }
                boundary = status.get("provider_boundary", {})
                if boundary.get("mode") != "local":
                    mismatches["provider_boundary.mode"] = {
                        "expected": "local",
                        "actual": boundary.get("mode"),
                    }
                if boundary.get("cloud_enabled") is not False:
                    mismatches["provider_boundary.cloud_enabled"] = {
                        "expected": False,
                        "actual": boundary.get("cloud_enabled"),
                    }
                if boundary.get("bridge_runtime_allowed") is not False:
                    mismatches["provider_boundary.bridge_runtime_allowed"] = {
                        "expected": False,
                        "actual": boundary.get("bridge_runtime_allowed"),
                    }
                if mismatches:
                    raise RuntimeArchiveError(
                        f"bundled MCP backend mismatch: {mismatches}"
                    )
                return {**counts, "status": expected_status}


def _launcher_command(bundle_root: Path) -> tuple[str, list[str]]:
    if os.name == "nt":
        launcher = bundle_root / "launchers" / "evermind.cmd"
        command = os.environ.get("COMSPEC") or shutil.which("cmd.exe")
        if not command or not launcher.is_file():
            raise RuntimeArchiveError(f"Windows launcher is missing: {launcher}")
        return command, ["/d", "/c", "call", str(launcher)]

    launcher = bundle_root / "launchers" / "evermind"
    command = shutil.which("sh")
    if not command or not launcher.is_file():
        raise RuntimeArchiveError(f"Unix launcher is missing: {launcher}")
    return command, [str(launcher)]


def _tool_payload(result) -> dict:
    value = result.structuredContent
    if value is None:
        if not result.content:
            raise RuntimeArchiveError("bundled MCP status returned no content")
        value = json.loads(result.content[0].text)
    if not isinstance(value, dict):
        raise RuntimeArchiveError("bundled MCP status returned a non-object payload")
    nested = value.get("result", value)
    if not isinstance(nested, dict):
        raise RuntimeArchiveError("bundled MCP status result is not an object")
    return nested


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract and smoke-test a complete EverMind runtime ZIP."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", type=Path)
    source.add_argument("--archive-directory", type=Path)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)
    archive = (
        args.archive
        if args.archive is not None
        else find_runtime_archive(args.archive_directory)
    )
    try:
        result = verify_runtime_archive(archive, timeout=args.timeout)
    except RuntimeArchiveError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
