"""EverMind native code graph tools."""
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
        edges: list[dict] = []
        for file in files:
            file_symbols, file_edges = _extract_file_graph(repo, file)
            symbols.extend(file_symbols)
            edges.extend(file_edges)
        edges = _resolve_graph_edges(symbols, edges)
        index = {
            "name": project,
            "root_path": str(repo),
            "indexed_at": int(time.time() * 1000),
            "files": [_file_record(repo, file) for file in files],
            "symbols": symbols,
            "edges": edges,
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
            edges=len(edges),
            file_count=len(files),
            files_indexed=len(files),
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
                    "edges": len(index.get("edges", [])),
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
            edge_count=len(index.get("edges", [])),
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
                results.append({"result_type": "symbol", **symbol})
            if len(results) >= limit:
                break
        if len(results) < limit:
            for edge in index.get("edges", []):
                haystack = " ".join(
                    str(edge.get(key, ""))
                    for key in ("type", "source", "target", "target_name", "file", "preview")
                ).casefold()
                if query in haystack:
                    results.append({"result_type": "edge", "kind": "edge", **edge})
                if len(results) >= limit:
                    break
        return _ok("search_graph", started, results=results, total=len(results), count=len(results))

    def get_graph_schema(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        kinds = sorted({str(symbol.get("kind")) for symbol in index.get("symbols", []) if symbol.get("kind")})
        edge_types = sorted({str(edge.get("type")) for edge in index.get("edges", []) if edge.get("type")})
        return _ok(
            "get_graph_schema",
            started,
            node_labels=["Project", "File", "Symbol", *kinds],
            edge_types=edge_types or ["DECLARES"],
            fallback_note="Native engine provides local file, symbol, import, inheritance, decorator, and Python call graph metadata.",
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
            total_edges=len(index.get("edges", [])),
            call_edges=len([edge for edge in index.get("edges", []) if edge.get("type") == "CALLS"]),
            languages=suffix_counts,
            top_level_dirs=top_dirs,
            entry_points=entry_points,
            hotspots=sorted(files, key=lambda item: item["size_bytes"], reverse=True)[:10],
            dependency_modules=_dependency_modules(index),
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
        depth = max(1, int(args.get("depth") or 1))
        direction = str(args.get("direction") or "both")
        callers = []
        callees = []
        if symbol:
            qualified_name = str(symbol["qualified_name"])
            if direction in {"both", "inbound"}:
                callers = _trace_calls(index, qualified_name, direction="inbound", depth=depth)
            if direction in {"both", "outbound"}:
                callees = _trace_calls(index, qualified_name, direction="outbound", depth=depth)
        return _ok(
            "trace_path",
            started,
            project=index["name"],
            function_name=function_name,
            symbol=symbol,
            callers=callers,
            callees=callees,
            edge_count=len(callers) + len(callees),
            fallback_note="Native engine infers Python call edges statically; dynamic dispatch and non-Python calls may be incomplete.",
        )

    def query_graph(self, args: dict, started: float) -> dict:
        index = _load_index(self.config, args)
        limit = int(args.get("limit") or 10)
        rows = [{"node": symbol} for symbol in index.get("symbols", [])[:limit]]
        if len(rows) < limit:
            rows.extend({"edge": edge} for edge in index.get("edges", [])[: limit - len(rows)])
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
        impacted = _impacted_symbols(index, changed)
        return _ok(
            "detect_changes",
            started,
            changed_files=changed,
            changed_count=len(changed),
            impacted_symbols=impacted,
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
        "engine": "evermind-code-graph",
        "fallback": "native",
        "native": True,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        **values,
    }


def _error(tool: str, code: str, message: str, retryable: bool = False) -> dict:
    return bridge_error_response(
        tool=tool,
        engine="evermind-code-graph",
        code=code,
        message=message,
        hint="EverMind internal code graph is active.",
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


def _extract_file_graph(root: Path, path: Path) -> tuple[list[dict], list[dict]]:
    text = _read_text(path)
    rel = _relative_path(root, path)
    if path.suffix.lower() == ".py":
        return _python_file_graph(rel, text)
    symbols = _regex_symbols(rel, text)
    edges = [_edge("DECLARES", rel, symbol["qualified_name"], rel, symbol["line"], symbol["preview"]) for symbol in symbols]
    return symbols, edges


def _extract_symbols(root: Path, path: Path) -> list[dict]:
    symbols, _edges = _extract_file_graph(root, path)
    return symbols


def _python_symbols(rel: str, text: str) -> list[dict]:
    symbols, _edges = _python_file_graph(rel, text)
    return symbols


def _python_file_graph(rel: str, text: str) -> tuple[list[dict], list[dict]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        symbols = _regex_symbols(rel, text)
        edges = [_edge("DECLARES", rel, symbol["qualified_name"], rel, symbol["line"], symbol["preview"]) for symbol in symbols]
        return symbols, edges

    visitor = _PythonGraphVisitor(rel, text)
    visitor.visit(tree)
    visitor.symbols.sort(key=lambda item: (item["file"], item["line"], item["name"]))
    visitor.edges.sort(key=lambda item: (item["file"], item.get("line") or 0, item["type"], item["source"], item["target"]))
    return visitor.symbols, visitor.edges


class _PythonGraphVisitor(ast.NodeVisitor):
    def __init__(self, rel: str, text: str) -> None:
        self.rel = rel
        self.lines = text.splitlines()
        self.name_stack: list[str] = []
        self.symbol_stack: list[str] = []
        self.symbols: list[dict] = []
        self.edges: list[dict] = []

    def visit_Import(self, node: ast.Import) -> None:
        source = self._current_source()
        for alias in node.names:
            self.edges.append(
                _edge("IMPORTS", source, alias.name, self.rel, node.lineno, self._line(node.lineno))
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        source = self._current_source()
        module = "." * int(node.level or 0) + (node.module or "")
        for alias in node.names:
            target = f"{module}.{alias.name}" if module else alias.name
            self.edges.append(
                _edge("IMPORTS", source, target, self.rel, node.lineno, self._line(node.lineno))
            )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        symbol = self._add_symbol(node, "class")
        for base in node.bases:
            target = _call_name(base)
            if target:
                self.edges.append(
                    _edge("EXTENDS", symbol["qualified_name"], target, self.rel, node.lineno, self._line(node.lineno), target_name=target)
                )
        self._add_decorator_edges(symbol["qualified_name"], node.decorator_list, node.lineno)
        self._visit_symbol_body(node, symbol["qualified_name"], node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, "function")

    def visit_Call(self, node: ast.Call) -> None:
        if self.symbol_stack:
            target = _call_name(node.func)
            if target:
                self.edges.append(
                    _edge(
                        "CALLS",
                        self.symbol_stack[-1],
                        target,
                        self.rel,
                        node.lineno,
                        self._line(node.lineno),
                        target_name=_target_symbol_name(target),
                        resolved=False,
                    )
                )
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
        if self.name_stack and self._stack_parent_is_class():
            kind = "method"
        symbol = self._add_symbol(node, kind)
        self._add_decorator_edges(symbol["qualified_name"], node.decorator_list, node.lineno)
        self._visit_symbol_body(node, symbol["qualified_name"], node.name)

    def _visit_symbol_body(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, qualified_name: str, name: str) -> None:
        self.name_stack.append(name)
        self.symbol_stack.append(qualified_name)
        for statement in node.body:
            self.visit(statement)
        self.symbol_stack.pop()
        self.name_stack.pop()

    def _add_symbol(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> dict:
        line = int(getattr(node, "lineno", 1))
        end_line = int(getattr(node, "end_lineno", line))
        symbol = _symbol(
            self.rel,
            node.name,
            kind,
            line,
            end_line,
            self._line(line),
            qualified_parts=[*self.name_stack, node.name],
        )
        self.symbols.append(symbol)
        self.edges.append(_edge("DECLARES", self.rel, symbol["qualified_name"], self.rel, line, self._line(line)))
        return symbol

    def _add_decorator_edges(self, source: str, decorators: list[ast.expr], line: int) -> None:
        for decorator in decorators:
            target = _call_name(decorator)
            if target:
                self.edges.append(
                    _edge("DECORATED_BY", source, target, self.rel, line, self._line(line), target_name=target)
                )

    def _current_source(self) -> str:
        return self.symbol_stack[-1] if self.symbol_stack else self.rel

    def _line(self, line: int) -> str:
        return self.lines[line - 1].strip() if 0 <= line - 1 < len(self.lines) else ""

    def _stack_parent_is_class(self) -> bool:
        if not self.symbol_stack:
            return False
        parent = self.symbol_stack[-1]
        return any(symbol["qualified_name"] == parent and symbol["kind"] == "class" for symbol in self.symbols)


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


def _symbol(
    rel: str,
    name: str,
    kind: str,
    line: int,
    end_line: int,
    preview: str,
    *,
    qualified_parts: list[str] | None = None,
) -> dict:
    suffix = ".".join(qualified_parts or [name])
    qualified_name = f"{rel.replace('/', '.').removesuffix('.py')}.{suffix}"
    return {
        "name": name,
        "qualified_name": qualified_name,
        "kind": kind,
        "file": rel,
        "line": line,
        "end_line": end_line,
        "preview": preview.strip(),
    }


def _edge(
    edge_type: str,
    source: str,
    target: str,
    file: str,
    line: int | None,
    preview: str = "",
    **extra: Any,
) -> dict:
    return {
        "type": edge_type,
        "source": source,
        "target": target,
        "file": file,
        "line": line,
        "preview": preview.strip(),
        **extra,
    }


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Subscript):
        return _call_name(node.value)
    return None


def _target_symbol_name(target: str) -> str:
    return target.rsplit(".", 1)[-1]


def _resolve_graph_edges(symbols: list[dict], edges: list[dict]) -> list[dict]:
    for edge in edges:
        if edge.get("type") not in {"CALLS", "EXTENDS", "DECORATED_BY"}:
            continue
        target_name = str(edge.get("target_name") or _target_symbol_name(str(edge.get("target", ""))))
        resolved = _resolve_symbol(symbols, edge, target_name)
        if resolved:
            edge["target"] = resolved["qualified_name"]
            edge["target_file"] = resolved["file"]
            edge["target_kind"] = resolved["kind"]
            edge["resolved"] = True
        else:
            edge.setdefault("resolved", False)
    return edges


def _resolve_symbol(symbols: list[dict], edge: dict, target_name: str) -> dict | None:
    candidates = [symbol for symbol in symbols if symbol.get("name") == target_name]
    if not candidates:
        return None

    source = str(edge.get("source") or "")
    source_symbol = next((symbol for symbol in symbols if symbol.get("qualified_name") == source), None)
    if source_symbol:
        same_file = [symbol for symbol in candidates if symbol.get("file") == source_symbol.get("file")]
        if same_file:
            parent = source.rsplit(".", 1)[0]
            same_parent = [
                symbol
                for symbol in same_file
                if str(symbol.get("qualified_name", "")).rsplit(".", 1)[0] == parent
            ]
            if same_parent:
                return same_parent[0]
            return same_file[0]

    same_file = [symbol for symbol in candidates if symbol.get("file") == edge.get("file")]
    if same_file:
        return same_file[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def _trace_calls(index: dict, qualified_name: str, *, direction: str, depth: int) -> list[dict]:
    edges = [edge for edge in index.get("edges", []) if edge.get("type") == "CALLS"]
    frontier = {qualified_name}
    seen_nodes = {qualified_name}
    seen_edges: set[tuple[str, str, int | None]] = set()
    results: list[dict] = []

    for hop in range(1, depth + 1):
        next_frontier: set[str] = set()
        for edge in edges:
            source = str(edge.get("source"))
            target = str(edge.get("target"))
            if direction == "outbound":
                matched = source in frontier
                node = target
            else:
                matched = target in frontier
                node = source
            if not matched:
                continue

            key = (source, target, edge.get("line"))
            if key not in seen_edges:
                seen_edges.add(key)
                results.append(_trace_item(edge, node, hop, direction))
            if edge.get("resolved") and node not in seen_nodes:
                seen_nodes.add(node)
                next_frontier.add(node)
        frontier = next_frontier
        if not frontier:
            break
    return results


def _trace_item(edge: dict, qualified_name: str, depth: int, direction: str) -> dict:
    return {
        "qualified_name": qualified_name,
        "name": _target_symbol_name(qualified_name),
        "direction": direction,
        "depth": depth,
        "file": edge.get("file"),
        "line": edge.get("line"),
        "resolved": bool(edge.get("resolved")),
        "edge": {
            "source": edge.get("source"),
            "target": edge.get("target"),
            "type": edge.get("type"),
        },
    }


def _dependency_modules(index: dict) -> list[str]:
    modules = set()
    for edge in index.get("edges", []):
        if edge.get("type") != "IMPORTS":
            continue
        target = str(edge.get("target") or "").lstrip(".")
        if target:
            modules.add(target.split(".", 1)[0])
    return sorted(modules)


def _impacted_symbols(index: dict, changed_files: list[str]) -> list[dict]:
    if not changed_files:
        return []
    changed = set(changed_files)
    direct = [
        symbol
        for symbol in index.get("symbols", [])
        if symbol.get("file") in changed
    ]
    impacted_names = {str(symbol.get("qualified_name")) for symbol in direct}
    for edge in index.get("edges", []):
        if edge.get("type") != "CALLS":
            continue
        if edge.get("source") in impacted_names:
            impacted_names.add(str(edge.get("target")))
        if edge.get("target") in impacted_names:
            impacted_names.add(str(edge.get("source")))

    symbols_by_name = {str(symbol.get("qualified_name")): symbol for symbol in index.get("symbols", [])}
    impacted = [symbols_by_name[name] for name in sorted(impacted_names) if name in symbols_by_name]
    return impacted


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
