"""Native fallback for Codebase Memory tools.

This intentionally covers the unified MCP contract without vendoring the
external codebase-memory-mcp engine. When the external binary is installed,
CodebaseEngine still delegates to it; this module is the no-binary fallback.
"""
from __future__ import annotations

import ast
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_v2 import EverMindConfig
from .tool_bridge import bridge_error_response


TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".cs",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".txt",
    ".ps1",
    ".sh",
    ".sql",
}

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",
    "generated",
}


@dataclass
class NativeCodebase:
    config: EverMindConfig

    def call(self, tool: str, arguments: dict | None = None) -> dict:
        args = arguments or {}
        started = time.perf_counter()
        try:
            if tool == "index_repository":
                return self.index_repository(args, started)
            if tool == "list_projects":
                return self.list_projects(started)
            if tool == "delete_project":
                return self.delete_project(args, started)
            if tool == "index_status":
                return self.index_status(args, started)
            if tool == "search_code":
                return self.search_code(args, started)
            if tool == "search_graph":
                return self.search_graph(args, started)
            if tool == "get_graph_schema":
                return self.get_graph_schema(args, started)
            if tool == "get_architecture":
                return self.get_architecture(args, started)
            if tool == "get_code_snippet":
                return self.get_code_snippet(args, started)
            if tool == "trace_path":
                return self.trace_path(args, started)
            if tool == "query_graph":
                return self.query_graph(args, started)
            if tool == "detect_changes":
                return self.detect_changes(args, started)
            if tool == "manage_adr":
                return self.manage_adr(args, started)
            if tool == "ingest_traces":
                return self.ingest_traces(args, started)
        except KeyError as exc:
            return _error(tool, "NATIVE_CODEBASE_INVALID_ARGUMENT", f"missing required argument: {exc.args[0]}")
        except ValueError as exc:
            return _error(tool, "NATIVE_CODEBASE_INVALID_ARGUMENT", str(exc))
        except OSError as exc:
            return _error(tool, "NATIVE_CODEBASE_IO_ERROR", str(exc), retryable=True)

        return _error(tool, "NATIVE_CODEBASE_UNKNOWN_TOOL", f"unknown codebase tool: {tool}")

    def index_repository(self, args: dict, started: float) -> dict:
        repo = Path(str(args["repo_path"])).resolve()
        if not repo.is_dir():
            raise ValueError(f"repo_path is not a directory: {repo}")
        project = str(args.get("project") or _project_name(repo))
        files = _scan_files(repo)
        symbols: list[dict] = []
        for file in files:
            symbols.extend(_extract_symbols(repo, file))
        index = {
            "name": project,
            "root_path": str(repo),
            "indexed_at": int(time.time() * 1000),
            "files": [_file_record(repo, file) for file in files],
            "symbols": symbols,
            "traces": [],
            "adr": [],
        }
        _write_index(self.config, project, index)
        return _ok(
            "index_repository",
            started,
            project=project,
            status="indexed",
            nodes=len(index["files"]) + len(symbols),
            edges=0,
            file_count=len(files),
            symbol_count=len(symbols),
        )

    def list_projects(self, started: float) -> dict:
        projects = []
        for path in _index_root(self.config).glob("*.json"):
            index = _read_index_path(path)
            if not index:
                continue
            projects.append(
                {
                    "name": index["name"],
                    "root_path": index["root_path"],
                    "nodes": len(index.get("files", [])) + len(index.get("symbols", [])),
                    "edges": 0,
                    "size_bytes": path.stat().st_size,
                    "fallback": "native",
                }
            )
        projects.sort(key=lambda item: item["name"])
        return _ok("list_projects", started, projects=projects, count=len(projects))

    def delete_project(self, args: dict, started: float) -> dict:
        path = _index_path(self.config, str(args["project"]))
        deleted = path.exists()
        if deleted:
            path.unlink()
        return _ok("delete_project", started, deleted=deleted, project=args["project"])

    def index_status(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        return _ok(
            "index_status",
            started,
            project=index["name"],
            status="indexed",
            root_path=index["root_path"],
            file_count=len(index.get("files", [])),
            symbol_count=len(index.get("symbols", [])),
            indexed_at=index.get("indexed_at"),
        )

    def search_code(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        pattern = str(args["pattern"])
        limit = int(args.get("limit") or 20)
        results = []
        for record in index.get("files", []):
            path = Path(index["root_path"]) / record["path"]
            text = _read_text(path)
            for line_no, line in enumerate(text.splitlines(), start=1):
                if pattern.casefold() in line.casefold():
                    results.append(
                        {
                            "file": record["path"],
                            "path": str(path),
                            "line": line_no,
                            "preview": line.strip(),
                            "score": line.casefold().count(pattern.casefold()),
                        }
                    )
                    break
            if len(results) >= limit:
                break
        return _ok("search_code", started, results=results, total_results=len(results), count=len(results))

    def search_graph(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        query = str(args["query"]).casefold()
        limit = int(args.get("limit") or 20)
        results = []
        for symbol in index.get("symbols", []):
            haystack = " ".join(
                str(symbol.get(key, "")) for key in ("name", "qualified_name", "file", "kind")
            ).casefold()
            if query in haystack:
                results.append(symbol)
            if len(results) >= limit:
                break
        return _ok("search_graph", started, results=results, total=len(results), count=len(results))

    def get_graph_schema(self, args: dict, started: float) -> dict:
        _load_index(self.config, args)
        return _ok(
            "get_graph_schema",
            started,
            node_labels=["Project", "File", "Symbol"],
            edge_types=["CONTAINS", "DECLARES"],
            fallback_note="Native fallback provides lightweight file/symbol graph metadata.",
        )

    def get_architecture(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        files = index.get("files", [])
        suffix_counts: dict[str, int] = {}
        top_dirs: dict[str, int] = {}
        for record in files:
            suffix_counts[record["suffix"]] = suffix_counts.get(record["suffix"], 0) + 1
            first = record["path"].split("/", 1)[0]
            top_dirs[first] = top_dirs.get(first, 0) + 1
        entry_points = [
            record["path"]
            for record in files
            if Path(record["path"]).name in {"main.py", "app.py", "server.py", "index.ts", "index.js"}
        ]
        return _ok(
            "get_architecture",
            started,
            project=index["name"],
            root_path=index["root_path"],
            total_files=len(files),
            total_symbols=len(index.get("symbols", [])),
            languages=suffix_counts,
            top_level_dirs=top_dirs,
            entry_points=entry_points,
            hotspots=sorted(files, key=lambda item: item["size_bytes"], reverse=True)[:10],
        )

    def get_code_snippet(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        qualified_name = str(args["qualified_name"])
        symbol = _find_symbol(index, qualified_name)
        if not symbol:
            raise ValueError(f"qualified_name not found: {qualified_name}")
        path = Path(index["root_path"]) / symbol["file"]
        lines = _read_text(path).splitlines()
        start_line = max(1, int(symbol.get("line", 1)) - (2 if args.get("include_neighbors") else 0))
        end_line = min(len(lines), int(symbol.get("end_line") or symbol.get("line") or 1) + (2 if args.get("include_neighbors") else 0))
        source = "\n".join(lines[start_line - 1 : end_line])
        return _ok(
            "get_code_snippet",
            started,
            project=index["name"],
            qualified_name=qualified_name,
            file=symbol["file"],
            start_line=start_line,
            end_line=end_line,
            source=source,
        )

    def trace_path(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        function_name = str(args["function_name"])
        symbol = _find_symbol(index, function_name)
        return _ok(
            "trace_path",
            started,
            project=index["name"],
            function_name=function_name,
            symbol=symbol,
            callers=[],
            callees=[],
            fallback_note="Native fallback does not infer call edges.",
        )

    def query_graph(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        limit = int(args.get("limit") or 10)
        rows = [{"node": symbol} for symbol in index.get("symbols", [])[:limit]]
        return _ok("query_graph", started, rows=rows, count=len(rows), query=args.get("query"))

    def detect_changes(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        root = Path(index["root_path"])
        old_files = {record["path"]: record for record in index.get("files", [])}
        current_files = {_relative_path(root, file): _file_record(root, file) for file in _scan_files(root)}
        changed = []
        for rel, record in current_files.items():
            previous = old_files.get(rel)
            if previous is None or previous.get("sha1") != record.get("sha1"):
                changed.append(rel)
        for rel in old_files:
            if rel not in current_files:
                changed.append(rel)
        changed = sorted(set(changed))
        return _ok(
            "detect_changes",
            started,
            changed_files=changed,
            changed_count=len(changed),
            impacted_symbols=[],
            depth=int(args.get("depth") or 2),
        )

    def manage_adr(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        mode = str(args.get("mode") or "list")
        adr = list(index.get("adr", []))
        if mode in {"store", "update", "create"}:
            entry = {
                "title": args.get("title") or "Untitled ADR",
                "content": args.get("content") or "",
                "updated_at": int(time.time() * 1000),
            }
            adr.append(entry)
            index["adr"] = adr
            _write_index(self.config, index["name"], index)
            return _ok("manage_adr", started, status="stored", adr=entry)
        return _ok("manage_adr", started, status="ok", adr=adr, count=len(adr))

    def ingest_traces(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        traces = list(index.get("traces", []))
        incoming = args.get("traces") or []
        if args.get("trace_path"):
            incoming.append({"trace_path": args["trace_path"]})
        traces.extend(incoming)
        index["traces"] = traces
        _write_index(self.config, index["name"], index)
        return _ok("ingest_traces", started, ingested=len(incoming), total=len(traces))


def _ok(tool: str, started: float, **values: Any) -> dict:
    return {
        "ok": True,
        "tool": tool,
        "engine": "codebase-memory-native",
        "fallback": "native",
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        **values,
    }


def _error(tool: str, code: str, message: str, retryable: bool = False) -> dict:
    return bridge_error_response(
        tool=tool,
        engine="codebase-memory-native",
        code=code,
        message=message,
        hint="Native fallback is active because codebase-memory-mcp executable was not found.",
        retryable=retryable,
    )


def _index_root(config: EverMindConfig) -> Path:
    root = config.home / "codebase-native"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _index_path(config: EverMindConfig, project: str) -> Path:
    return _index_root(config) / f"{_safe_slug(project)}.json"


def _write_index(config: EverMindConfig, project: str, index: dict) -> None:
    path = _index_path(config, project)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_index_path(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_index(config: EverMindConfig, args: dict) -> dict:
    project = args.get("project")
    if not project and args.get("repo_path"):
        repo = Path(str(args["repo_path"])).resolve()
        matched = _find_index_by_root(config, repo)
        if matched:
            return matched
        project = _project_name(repo)
    if not project:
        raise ValueError("project or repo_path is required")
    path = _index_path(config, str(project))
    if not path.exists():
        raise ValueError(f"project not indexed in native fallback: {project}")
    index = _read_index_path(path)
    if not index:
        raise ValueError(f"native index is unreadable: {project}")
    return index


def _find_index_by_root(config: EverMindConfig, repo: Path) -> dict | None:
    normalized = repo.resolve().as_posix().casefold()
    for path in _index_root(config).glob("*.json"):
        index = _read_index_path(path)
        if not index:
            continue
        root_path = index.get("root_path")
        if root_path and Path(str(root_path)).resolve().as_posix().casefold() == normalized:
            return index
    return None


def _scan_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.stat().st_size > 1_000_000:
            continue
        files.append(path)
    return sorted(files)


def _file_record(root: Path, path: Path) -> dict:
    text = _read_text(path)
    return {
        "path": _relative_path(root, path),
        "suffix": path.suffix.lower(),
        "size_bytes": path.stat().st_size,
        "sha1": _sha1(text),
        "line_count": len(text.splitlines()),
    }


def _extract_symbols(root: Path, path: Path) -> list[dict]:
    text = _read_text(path)
    rel = _relative_path(root, path)
    if path.suffix.lower() == ".py":
        return _python_symbols(rel, text)
    return _regex_symbols(rel, text)


def _python_symbols(rel: str, text: str) -> list[dict]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _regex_symbols(rel, text)
    lines = text.splitlines()
    symbols = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        line = int(getattr(node, "lineno", 1))
        end_line = int(getattr(node, "end_lineno", line))
        symbols.append(_symbol(rel, node.name, kind, line, end_line, lines[line - 1] if lines else ""))
    symbols.sort(key=lambda item: (item["file"], item["line"], item["name"]))
    return symbols


def _regex_symbols(rel: str, text: str) -> list[dict]:
    symbols = []
    pattern = re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:function|class|def)\s+([A-Za-z_][A-Za-z0-9_]*)",
        re.MULTILINE,
    )
    lines = text.splitlines()
    for match in pattern.finditer(text):
        line = text[: match.start()].count("\n") + 1
        raw = lines[line - 1] if 0 <= line - 1 < len(lines) else ""
        kind = "class" if "class" in raw.split()[:2] else "function"
        symbols.append(_symbol(rel, match.group(1), kind, line, line, raw))
    return symbols


def _symbol(rel: str, name: str, kind: str, line: int, end_line: int, preview: str) -> dict:
    qualified_name = f"{rel.replace('/', '.').removesuffix('.py')}.{name}"
    return {
        "name": name,
        "qualified_name": qualified_name,
        "kind": kind,
        "file": rel,
        "line": line,
        "end_line": end_line,
        "preview": preview.strip(),
    }


def _find_symbol(index: dict, qualified_name: str) -> dict | None:
    needle = qualified_name.casefold()
    for symbol in index.get("symbols", []):
        if needle in {str(symbol.get("qualified_name", "")).casefold(), str(symbol.get("name", "")).casefold()}:
            return symbol
    for symbol in index.get("symbols", []):
        if needle in str(symbol.get("qualified_name", "")).casefold():
            return symbol
    return None


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _project_name(repo: Path) -> str:
    return _safe_slug(str(repo.resolve()).replace(":", "").replace("\\", "-").replace("/", "-"))


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip())
    return slug.strip("-._") or "project"


def _sha1(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
