"""Adapter for the vendored codebase-memory-mcp engine."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .config_v2 import EverMindConfig
from .tool_bridge import bridge_error_response


EXPECTED_TREE_SITTER_GRAMMAR_COUNT = 159
REQUIRED_HYBRID_LSP_FILES = (
    "py_lsp.c",
    "ts_lsp.c",
    "php_lsp.c",
    "cs_lsp.c",
    "go_lsp.c",
    "c_lsp.c",
    "java_lsp.c",
    "kotlin_lsp.c",
    "rust_lsp.c",
)


@dataclass
class VendoredCodebase:
    config: EverMindConfig

    def metadata(self) -> dict:
        source = self.config.codebase_source_dir
        binary = self._binary_path()
        integrity = self._source_integrity()
        return {
            "backend": "vendored-codebase-memory-mcp",
            "source_integrated": integrity["ok"],
            "source_path": str(source),
            "binary_available": binary.is_file(),
            "binary_path": str(binary),
            "build_target": "make -f Makefile.cbm cbm",
            "license": "MIT",
            "tree_sitter_grammar_count": integrity["tree_sitter_grammar_count"],
            "expected_tree_sitter_grammar_count": EXPECTED_TREE_SITTER_GRAMMAR_COUNT,
            "hybrid_lsp_files_present": integrity["hybrid_lsp_files_present"],
            "hybrid_lsp_required_files": list(REQUIRED_HYBRID_LSP_FILES),
            "missing_source_files": integrity["missing_source_files"],
        }

    @property
    def source_available(self) -> bool:
        return self._source_integrity()["ok"]

    @property
    def available(self) -> bool:
        return self.source_available and self._binary_path().is_file()

    def call(self, tool: str, arguments: dict | None = None) -> dict:
        args = dict(arguments or {})
        workspace_id = args.pop("_evermind_workspace_id", None)
        display_name = args.pop("_evermind_display_name", None)
        project_id = args.pop("_evermind_project_id", None)
        if tool == "index_repository" and args.get("repo_path"):
            display_name = display_name or str(
                args.get("project")
                or args.get("name")
                or Path(str(args["repo_path"])).name
            )
            workspace_id = workspace_id or _workspace_id(str(args["repo_path"]))
            args["name"] = workspace_id
        started = time.perf_counter()
        binary = self._binary_path()
        if not binary.is_file():
            return (
                bridge_error_response(
                    tool=tool,
                    engine="evermind-code-graph",
                    code="CODEBASE_VENDORED_BINARY_MISSING",
                    message="vendored codebase-memory-mcp source is present but the internal binary has not been built",
                    hint="Build the in-repo engine with scripts/build-vendored-codebase.ps1 or scripts/build-vendored-codebase.sh.",
                    retryable=False,
                    latency_ms=_elapsed_ms(started),
                )
                | self.metadata()
            )

        command = [str(binary), "cli", "--json", tool]
        try:
            proc = subprocess.run(
                command,
                input=json.dumps(args, ensure_ascii=False),
                cwd=str(self.config.codebase_source_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.config.codebase_cli_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return (
                bridge_error_response(
                    tool=tool,
                    engine="evermind-code-graph",
                    code="CODEBASE_VENDORED_TIMEOUT",
                    message=f"vendored codebase engine timed out after {self.config.codebase_cli_timeout_seconds}s",
                    hint="Retry with a smaller repository or increase EVERMIND_CODEBASE_CLI_TIMEOUT_SECONDS.",
                    retryable=True,
                    latency_ms=_elapsed_ms(started),
                )
                | self.metadata()
            )
        except OSError as exc:
            return (
                bridge_error_response(
                    tool=tool,
                    engine="evermind-code-graph",
                    code="CODEBASE_VENDORED_EXEC_ERROR",
                    message=str(exc),
                    hint="Check the in-repo codebase-memory-mcp build output.",
                    retryable=True,
                    latency_ms=_elapsed_ms(started),
                )
                | self.metadata()
            )

        if proc.returncode != 0:
            return (
                bridge_error_response(
                    tool=tool,
                    engine="evermind-code-graph",
                    code="CODEBASE_VENDORED_FAILED",
                    message=_first_nonempty(
                        proc.stderr,
                        proc.stdout,
                        f"codebase engine exited with {proc.returncode}",
                    ),
                    hint="The bundled codebase-memory-mcp process returned a non-zero exit code.",
                    retryable=False,
                    returncode=proc.returncode,
                    stdout=proc.stdout[-4000:],
                    stderr=proc.stderr[-4000:],
                    latency_ms=_elapsed_ms(started),
                )
                | self.metadata()
            )

        payload = _parse_output(proc.stdout)
        if payload is None:
            return (
                bridge_error_response(
                    tool=tool,
                    engine="evermind-code-graph",
                    code="CODEBASE_VENDORED_BAD_JSON",
                    message="vendored codebase engine returned non-JSON output",
                    hint="Run the bundled binary with piped JSON input to inspect the raw response.",
                    stdout=proc.stdout[-4000:],
                    stderr=proc.stderr[-4000:],
                    latency_ms=_elapsed_ms(started),
                )
                | self.metadata()
            )

        result = _normalize_success(tool, payload, started, self.metadata())
        if workspace_id:
            result["project"] = workspace_id
            result["workspace_id"] = workspace_id
            result["display_name"] = display_name
        if project_id:
            result["project_id"] = project_id
        return result

    def _binary_path(self) -> Path:
        path = self.config.codebase_binary_path
        if path.is_file():
            return path
        if os.name == "nt" and path.suffix.lower() != ".exe":
            exe = path.with_suffix(".exe")
            if exe.is_file():
                return exe
        if os.name == "nt" and path.suffix.lower() == ".exe":
            bare = path.with_suffix("")
            if bare.is_file():
                return bare
        return path

    def _source_integrity(self) -> dict:
        source = self.config.codebase_source_dir
        cbm = source / "internal" / "cbm"
        grammars = cbm / "vendored" / "grammars"
        lsp = cbm / "lsp"
        required = [
            source / "LICENSE",
            source / "THIRD_PARTY.md",
            source / "README.md",
            source / "Makefile.cbm",
            source / "src" / "mcp" / "mcp.c",
            cbm / "cbm.c",
            cbm / "lsp_all.c",
            grammars / "MANIFEST.md",
            cbm / "vendored" / "ts_runtime" / "include" / "tree_sitter" / "api.h",
        ]
        required.extend(lsp / name for name in REQUIRED_HYBRID_LSP_FILES)
        missing = [str(path) for path in required if not path.is_file()]
        grammar_count = _count_child_dirs(grammars)
        present_lsp = [
            name for name in REQUIRED_HYBRID_LSP_FILES if (lsp / name).is_file()
        ]
        return {
            "ok": (
                source.is_dir()
                and not missing
                and grammar_count >= EXPECTED_TREE_SITTER_GRAMMAR_COUNT
                and len(present_lsp) == len(REQUIRED_HYBRID_LSP_FILES)
            ),
            "tree_sitter_grammar_count": grammar_count,
            "hybrid_lsp_files_present": present_lsp,
            "missing_source_files": missing,
        }


def _normalize_success(
    tool: str, payload: dict, started: float, metadata: dict
) -> dict:
    result = dict(payload)
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        for key, value in structured.items():
            result.setdefault(key, value)
    elif isinstance(result.get("content"), list):
        parsed = _parse_content_json(result["content"])
        if parsed:
            for key, value in parsed.items():
                result.setdefault(key, value)
    result.setdefault("ok", not bool(result.get("error")))
    result.setdefault("tool", tool)
    result["engine"] = "evermind-code-graph"
    result["backend"] = "vendored-codebase-memory-mcp"
    result["native"] = True
    result["fallback"] = "vendored"
    result["source_integrated"] = metadata["source_integrated"]
    result["binary_path"] = metadata["binary_path"]
    result["tree_sitter_grammar_count"] = metadata["tree_sitter_grammar_count"]
    result["expected_tree_sitter_grammar_count"] = metadata[
        "expected_tree_sitter_grammar_count"
    ]
    result["hybrid_lsp_files_present"] = metadata["hybrid_lsp_files_present"]
    result["hybrid_lsp_required_files"] = metadata["hybrid_lsp_required_files"]
    result["latency_ms"] = _elapsed_ms(started)
    return result


def _parse_content_json(content: list) -> dict | None:
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _parse_output(stdout: str) -> dict | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else {"results": payload}


def _first_nonempty(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _count_child_dirs(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for child in path.iterdir() if child.is_dir())


def _workspace_id(repo_path: str) -> str:
    canonical = os.path.normcase(str(Path(repo_path).expanduser().resolve()))
    return f"ws-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"
