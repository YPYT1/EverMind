"""EverMind bridge for the Codebase Memory graph engine."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config_v2 import EverMindConfig
from .native_codebase import NativeCodebase
from .tool_bridge import bridge_error_response, bridge_failure_response, resolve_executable, run_json_command


CODEBASE_TOOL_NAMES = {
    "index_repository",
    "list_projects",
    "delete_project",
    "index_status",
    "search_graph",
    "trace_path",
    "detect_changes",
    "query_graph",
    "get_graph_schema",
    "get_code_snippet",
    "get_architecture",
    "search_code",
    "manage_adr",
    "ingest_traces",
}


@dataclass
class CodebaseEngine:
    config: EverMindConfig

    @property
    def executable(self) -> str | None:
        return resolve_executable(
            self.config.codebase_memory_path,
            "codebase-memory-mcp",
        )

    def call(self, tool: str, arguments: dict | None = None) -> dict:
        if tool not in CODEBASE_TOOL_NAMES:
            return bridge_error_response(
                tool=tool,
                engine="codebase-memory-mcp",
                code="CODEBASE_UNKNOWN_TOOL",
                message=f"unknown codebase tool: {tool}",
            )

        executable = self.executable
        if executable is None:
            return NativeCodebase(self.config).call(tool, arguments or {})

        normalized_args = _normalize_arguments(tool, arguments or {})
        if (
            tool == "detect_changes"
            and not normalized_args.get("project")
            and normalized_args.get("repo_path")
        ):
            normalized_args["project"] = _project_name_from_repo_path(
                executable,
                str(normalized_args["repo_path"]),
                self.config.codebase_timeout_seconds,
            )

        payload = json.dumps(normalized_args, ensure_ascii=False)
        result = run_json_command(
            [executable, "cli", tool, payload],
            timeout_seconds=self.config.codebase_timeout_seconds,
        )
        response = result.to_dict()
        response["tool"] = tool
        response["engine"] = "codebase-memory-mcp"
        if result.ok:
            return _unwrap_bridge_response(response)
        return bridge_failure_response(
            result,
            tool=tool,
            engine="codebase-memory-mcp",
            hint="Check codebase-memory-mcp installation, project name, and repository indexing status.",
        )


def _unwrap_bridge_response(response: dict) -> dict:
    data = response.get("data")
    if isinstance(data, dict):
        merged = dict(data)
        merged.setdefault("ok", True)
        merged.setdefault("engine", response["engine"])
        merged.setdefault("tool", response["tool"])
        merged.setdefault("latency_ms", response["latency_ms"])
        return merged
    response["ok"] = True
    return response


def _normalize_arguments(tool: str, arguments: dict) -> dict:
    normalized = dict(arguments)
    return normalized


def _project_name_from_repo_path(
    executable: str,
    repo_path: str,
    timeout_seconds: float,
) -> str:
    list_result = run_json_command(
        [executable, "cli", "list_projects", "{}"],
        timeout_seconds=timeout_seconds,
    )
    projects = _projects_from_result(list_result)
    normalized_repo = _normalize_repo_path(repo_path)
    for project in projects:
        if not isinstance(project, dict):
            continue
        root_path = project.get("root_path")
        name = project.get("name")
        if root_path and name and _normalize_repo_path(str(root_path)) == normalized_repo:
            return str(name)
    return Path(repo_path).name


def _projects_from_result(result: object) -> list[dict]:
    if not getattr(result, "ok", False):
        return []
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        projects = data.get("projects")
        if isinstance(projects, list):
            return projects
    return []


def _normalize_repo_path(path: str) -> str:
    return Path(path).resolve().as_posix().rstrip("/").casefold()
