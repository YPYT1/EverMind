"""EverMind MCP Server v2 — unified memory, code graph, and archive interface."""

from __future__ import annotations

from contextlib import asynccontextmanager
from functools import wraps
import hashlib
import inspect
import json
import logging
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_context
from fastmcp.tools import FunctionTool
from mcp import types

from basic_memory.mcp.prompts.continue_conversation import continue_conversation
from basic_memory.mcp.prompts.recent_activity import recent_activity_prompt
from basic_memory.mcp.prompts.search import search_prompt
from basic_memory.mcp.prompts.ai_assistant_guide import ai_assistant_guide
from basic_memory.mcp.resources.project_info import project_info
from basic_memory.mcp.tools import (
    build_context,
    canvas,
    create_memory_project,
    delete_note,
    edit_note,
    fetch,
    list_directory,
    list_memory_projects,
    move_note,
    read_content,
    read_note,
    recent_activity,
    release_notes,
    schema_diff,
    schema_infer,
    schema_validate,
    search,
    search_notes,
    view_note,
    write_note,
)

from .memory_service_v2 import MemoryService
from .archive_engine import ARCHIVE_TOOL_NAMES, archive_project_path
from .codebase_engine import CODEBASE_TOOL_NAMES
from .tool_errors import tool_error_response

logger = logging.getLogger(__name__)

_svc: MemoryService | None = None
_last_roots_space: str | None = None

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def _tool(name: str, schema: dict) -> types.Tool:
    input_schema = {
        "type": "object",
        "properties": schema["properties"],
        "required": schema.get("required", []),
    }
    for keyword in ("anyOf", "oneOf", "allOf"):
        if keyword in schema:
            input_schema[keyword] = schema[keyword]
    return types.Tool(
        name=name,
        description=schema["description"],
        inputSchema=input_schema,
    )


MEMORY_TOOLS: list[types.Tool] = [
    types.Tool(
        name="remember",
        description=(
            "Save information to memory. The system automatically assigns the memory layer "
            "(working/episodic/semantic/procedural/archive) and type (bug/decision/preference/etc) "
            "based on content and importance. "
            "importance=0: working memory (auto-expires in 24h). "
            "importance=1: long-term memory. "
            "importance=2: permanent archive."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to remember",
                },
                "importance": {
                    "type": "integer",
                    "enum": [0, 1, 2],
                    "default": 0,
                    "description": "0=working(24h), 1=long-term, 2=permanent",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Optional tags for categorization",
                },
                "memory_type": {
                    "type": "string",
                    "enum": [
                        "auto",
                        "episodic",
                        "semantic",
                        "procedural",
                        "decision",
                        "bug",
                        "preference",
                    ],
                    "default": "auto",
                },
                "meta": {
                    "type": "object",
                    "default": {},
                    "description": "Optional metadata, e.g. {'source':'codebase','verified_at':'2026-07-09T00:00:00Z'}",
                },
            },
            "required": ["content"],
        },
    ),
    types.Tool(
        name="update_memory",
        description=(
            "Update an existing EverMind memory by ID. Use when a memory is wrong, stale, "
            "or needs verified metadata/tags. Content changes create a new current version "
            "and retain the prior version as history. Rebuilds FTS, embeddings, graph links, "
            "and briefing cache as needed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Memory ID from recall(), list(), graph_explore(), or briefing()",
                },
                "content": {
                    "type": "string",
                    "description": "Replacement memory content",
                },
                "importance": {
                    "type": "integer",
                    "enum": [0, 1, 2],
                    "description": "Optional new importance: 0=working, 1=long-term, 2=archive",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional replacement tag list",
                },
                "memory_type": {
                    "type": "string",
                    "enum": [
                        "auto",
                        "episodic",
                        "semantic",
                        "procedural",
                        "decision",
                        "bug",
                        "preference",
                    ],
                    "description": "Optional replacement type; auto re-detects from content",
                },
                "meta": {
                    "type": "object",
                    "description": "Optional replacement metadata, e.g. {'source':'codebase'}",
                },
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="recall",
        description=(
            "Search memory using hybrid BM25 + semantic search (falls back to keyword-only if vector "
            "search not installed). Automatically searches the current project space. Returns memories "
            "ranked by relevance. Use before starting a feature, investigating a bug, or when unsure "
            "about a prior decision. Parameters: query (what to search), limit (max results, default 10), "
            "mode (hybrid/fts/semantic), layer (filter by memory layer), tags (filter by tags)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "mode": {
                    "type": "string",
                    "enum": ["hybrid", "fts", "semantic"],
                    "default": "hybrid",
                },
                "layer": {
                    "type": "string",
                    "enum": [
                        "working",
                        "episodic",
                        "semantic",
                        "procedural",
                        "archive",
                    ],
                    "description": "Filter by memory layer (optional)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags (optional)",
                },
                "space": {
                    "type": "string",
                    "description": "Optional: override the auto-detected project space",
                },
                "all_spaces": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, search across ALL known project spaces",
                },
                "include_expired": {
                    "type": "boolean",
                    "default": False,
                },
                "min_score": {
                    "type": "number",
                    "default": 0.15,
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Minimum final relevance score. Set 0 to return all ranked candidates.",
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="forget",
        description=(
            "Delete a specific memory by ID. Get the memory ID from the id field in recall() or "
            "briefing() results. Use when a memory is outdated, incorrect, or should not appear in "
            "future searches."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "Memory ID to delete",
                },
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="briefing",
        description=(
            "Get session context: recent memories and important long-term knowledge for the "
            "current project. Call this at the start of every coding session to restore project context. "
            "If memory_count is 0 in the response, this is a new project — explore the codebase with "
            "evermind-code-graph and call remember() to seed initial memories."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "fast": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, skip synchronous LLM summary and return cached structured context.",
                },
            },
            "required": [],
        },
    ),
    types.Tool(
        name="list",
        description=(
            "Browse stored memories filtered by layer or tags. Use to audit what is in memory, "
            "find archive-layer decisions, or see all procedural memories. If no filters given, "
            "returns most recent and important memories."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "enum": [
                        "working",
                        "episodic",
                        "semantic",
                        "procedural",
                        "archive",
                    ],
                    "description": "Filter by layer (optional)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by tags (optional)",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Max results",
                },
            },
            "required": [],
        },
    ),
    types.Tool(
        name="graph_explore",
        description=(
            "Find all memories related to a specific entity (file, class, function, module, concept). "
            "EverMind automatically extracts entities from memories and builds a relationship graph. "
            "Use to find everything known about 'auth.py', 'UserService', or any named concept."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity name to search for (file path, class name, function name, module name)",
                },
            },
            "required": ["entity"],
        },
    ),
    types.Tool(
        name="status",
        description="Show EverMind system status: memory counts by layer, embedding availability, search mode, jieba Chinese FTS status, all known project spaces. Call to understand the current state of EverMind.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="export",
        description="Export all memories or a specific layer as Markdown or JSON. Use to audit stored knowledge, share project context, or create documentation from accumulated memory.",
        inputSchema={
            "type": "object",
            "properties": {
                "layer": {
                    "type": "string",
                    "enum": [
                        "working",
                        "episodic",
                        "semantic",
                        "procedural",
                        "archive",
                    ],
                    "description": "Export only this layer (optional)",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json"],
                    "default": "markdown",
                },
            },
            "required": [],
        },
    ),
    types.Tool(
        name="compact",
        description="Compact old episodic memories into a semantic summary. Finds episodic memories older than the specified days and merges them. Useful for long-running projects where stale memories pollute recall results.",
        inputSchema={
            "type": "object",
            "properties": {
                "older_than_days": {
                    "type": "integer",
                    "default": 30,
                    "minimum": 1,
                    "description": "Compact episodic memories older than this many days",
                },
            },
            "required": [],
        },
    ),
    types.Tool(
        name="tags",
        description="List all tags currently in use in this project. Use to discover available tag categories before filtering with recall(tags=[...]) or list(tags=[...]).",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="reindex",
        description="Rebuild the FTS index using the current tokenizer. Use after installing jieba or when Chinese keyword search misses old memories.",
        inputSchema={
            "type": "object",
            "properties": {
                "all_spaces": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, rebuild FTS indexes for all spaces in the current database.",
                },
            },
            "required": [],
        },
    ),
    types.Tool(
        name="health",
        description="Show memory health metrics: embedding coverage, FTS coverage, queue state, duplicates, expired working memories, and model availability.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="list_spaces",
        description="List all project spaces known to this local EverMind database and show the current space.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
]

CODEBASE_TOOL_SCHEMAS: dict[str, dict] = {
    "index_repository": {
        "description": "Index a repository into the built-in EverMind code graph engine.",
        "properties": {
            "repo_path": {"type": "string", "description": "Absolute repository path"},
            "project": {
                "type": "string",
                "description": "Optional explicit project name",
            },
        },
        "required": ["repo_path"],
    },
    "list_projects": {
        "description": "List all indexed EverMind code graph projects.",
        "properties": {},
        "required": [],
    },
    "delete_project": {
        "description": "Detach one unified local project and its derived indexes while preserving repositories, Markdown notes, and durable memories.",
        "properties": {
            "project": {"type": "string"},
            "project_name": {"type": "string"},
        },
        "anyOf": [
            {"required": ["project"]},
            {"required": ["project_name"]},
        ],
    },
    "index_status": {
        "description": "Get EverMind code graph indexing status for a project.",
        "properties": {
            "project": {"type": "string"},
            "repo_path": {"type": "string"},
        },
        "required": [],
    },
    "search_graph": {
        "description": "Search code graph symbols and relationships.",
        "properties": {
            "project": {"type": "string"},
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["project", "query"],
    },
    "trace_path": {
        "description": "Trace callers/callees for a function or qualified symbol.",
        "properties": {
            "project": {"type": "string"},
            "function_name": {"type": "string"},
            "depth": {"type": "integer"},
        },
        "required": ["project", "function_name"],
    },
    "detect_changes": {
        "description": "Analyze git working-tree changes and graph impact. Prefer project; repo_path is accepted and used to infer project when omitted.",
        "properties": {
            "repo_path": {"type": "string"},
            "project": {"type": "string"},
        },
        "required": [],
    },
    "query_graph": {
        "description": "Run an advanced graph query against an indexed project.",
        "properties": {
            "project": {"type": "string"},
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["project", "query"],
    },
    "get_graph_schema": {
        "description": "Return node labels, edge types, and graph schema for a project.",
        "properties": {"project": {"type": "string"}},
        "required": ["project"],
    },
    "get_code_snippet": {
        "description": "Read source for an exact qualified_name found via search_graph.",
        "properties": {
            "project": {"type": "string"},
            "qualified_name": {"type": "string"},
            "include_neighbors": {"type": "boolean", "default": False},
        },
        "required": ["project", "qualified_name"],
    },
    "get_architecture": {
        "description": "Get architecture overview: modules, entry points, hotspots, layers, and tree.",
        "properties": {
            "project": {"type": "string"},
            "aspects": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["project"],
    },
    "search_code": {
        "description": "Search source text/patterns in an indexed project.",
        "properties": {
            "project": {"type": "string"},
            "pattern": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["project", "pattern"],
    },
    "manage_adr": {
        "description": "Create, update, or read Architecture Decision Records for a project.",
        "properties": {
            "project": {"type": "string"},
            "mode": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["project", "mode"],
    },
    "ingest_traces": {
        "description": "Ingest runtime traces to validate and enrich code graph edges.",
        "properties": {
            "project": {"type": "string"},
            "trace_path": {"type": "string"},
            "traces": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["project"],
    },
}

CANDIDATE_TOOL_SCHEMAS: dict[str, dict] = {
    "propose_basic_memory_update": {
        "description": "Write a reviewed EverMind archive candidate; does not modify formal notes.",
        "properties": {
            "project_slug": {"type": "string"},
            "target_file": {"type": "string"},
            "content": {"type": "string"},
            "evidence": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["project_slug", "target_file", "content"],
    },
    "commit_basic_memory_update": {
        "description": "Commit an EverMind archive candidate only when confirmed=true.",
        "properties": {
            "candidate_id": {"type": "string"},
            "confirmed": {"type": "boolean", "default": False},
        },
        "required": ["candidate_id", "confirmed"],
    },
}

BASIC_TOOL_FUNCTIONS = (
    build_context,
    canvas,
    create_memory_project,
    delete_note,
    edit_note,
    fetch,
    list_directory,
    list_memory_projects,
    move_note,
    read_content,
    read_note,
    recent_activity,
    release_notes,
    schema_diff,
    schema_infer,
    schema_validate,
    search,
    search_notes,
    view_note,
    write_note,
)
FAST_CORE_TOOLS = [
    *MEMORY_TOOLS,
    *[_tool(name, CODEBASE_TOOL_SCHEMAS[name]) for name in sorted(CODEBASE_TOOL_NAMES)],
    *[_tool(name, CANDIDATE_TOOL_SCHEMAS[name]) for name in sorted(ARCHIVE_TOOL_NAMES)],
]

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _dispatch_core_tool(
    name: str, arguments: dict | None, context: Context | None = None
) -> dict:
    args = arguments or {}

    try:
        if _svc is None:
            raise RuntimeError("MemoryService not initialised")

        await _maybe_update_space_from_roots(context)

        if name == "remember":
            result = await _svc.remember(
                content=args["content"],
                importance=args.get("importance", 0),
                tags=args.get("tags", []),
                memory_type=args.get("memory_type", "auto"),
                meta=args.get("meta"),
            )

        elif name == "update_memory":
            result = await _svc.update_memory(
                memory_id=args["id"],
                content=args.get("content"),
                importance=args.get("importance"),
                tags=args.get("tags"),
                memory_type=args.get("memory_type"),
                meta=args.get("meta"),
            )

        elif name == "recall":
            all_spaces = bool(args.get("all_spaces", False))
            space_override = args.get("space")
            result = await _svc.recall(
                query=args["query"],
                limit=args.get("limit", 10),
                mode=args.get("mode", "hybrid"),
                layer=args.get("layer"),
                tags=args.get("tags"),
                all_spaces=all_spaces,
                space=space_override,
                min_score=args.get("min_score"),
                include_expired=bool(args.get("include_expired", False)),
            )

        elif name == "forget":
            result = await _svc.forget(memory_id=args["id"])

        elif name == "briefing":
            result = await _svc.briefing(fast=bool(args.get("fast", True)))

        elif name == "list":
            result = await _svc.list_memories(
                layer=args.get("layer"),
                tags=args.get("tags"),
                limit=args.get("limit", 20),
            )

        elif name == "graph_explore":
            result = await _svc.graph_explore(args["entity"])

        elif name == "status":
            result = await _svc.status()

        elif name == "export":
            layer = args.get("layer")
            fmt = args.get("format", "markdown")
            result = await _svc.export(layer=layer, format=fmt)

        elif name == "compact":
            older = int(args.get("older_than_days", 30))
            result = await _svc.compact(older_than_days=older)

        elif name == "tags":
            result = await _svc.list_tags()

        elif name == "reindex":
            result = await _svc.reindex(all_spaces=bool(args.get("all_spaces", False)))

        elif name == "health":
            result = await _svc.health()

        elif name == "list_spaces":
            result = await _svc.list_spaces()

        elif name == "delete_project":
            result = await _svc.delete_project(
                project=args.get("project"),
                project_name=args.get("project_name"),
                remove_basic_project=_remove_basic_project,
            )

        elif name in CODEBASE_TOOL_NAMES:
            result = _svc.call_codebase(name, args)

        elif name in ARCHIVE_TOOL_NAMES:
            result = _svc.call_archive(name, args)

        else:
            result = tool_error_response(
                tool=name,
                engine="evermind-mcp",
                code="MCP_UNKNOWN_TOOL",
                message=f"unknown MCP tool: {name}",
                hint="Call list_tools first and use one of the registered EverMind MCP tool names.",
            )

    except KeyError as exc:
        missing = str(exc.args[0])
        result = tool_error_response(
            tool=name,
            engine="evermind-mcp",
            code="MCP_INVALID_ARGUMENT",
            message=f"missing required argument: {missing}",
            hint="Check the tool input schema and provide all required arguments.",
        )

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        result = tool_error_response(
            tool=name,
            engine="evermind-mcp",
            code="MCP_TOOL_EXCEPTION",
            message=str(exc),
            hint="Check the tool input schema and EverMind logs for details.",
        )

    return result


def _fast_core_tool(tool: types.Tool) -> FunctionTool:
    async def invoke(**arguments):
        try:
            context = get_context()
        except RuntimeError:
            context = None
        result = await _dispatch_core_tool(tool.name, arguments, context)
        if isinstance(result, dict) and result.get("ok") is False:
            raise ToolError(json.dumps(result, ensure_ascii=False))
        return result

    return FunctionTool(
        name=tool.name,
        description=tool.description,
        parameters=tool.inputSchema,
        fn=invoke,
        return_type=dict,
        run_in_thread=False,
    )


def _basic_project_name(project_id: str) -> str:
    if re.fullmatch(r"prj-[0-9a-f]+", project_id):
        return project_id
    digest = hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:24]
    return f"project-{digest}"


async def _ensure_basic_project(identifier: str) -> str:
    from basic_memory.config import ConfigManager, ProjectEntry
    from basic_memory.services.initialization import initialize_app

    if _svc is None:
        raise RuntimeError("MemoryService not initialised")
    project = _svc.projects.resolve_project(identifier)
    project_id = project["project_id"]
    binding = _svc.storage.conn.execute(
        "SELECT basic_name, basic_path FROM basic_project_bindings WHERE project_id=?",
        (project_id,),
    ).fetchone()
    basic_name = binding["basic_name"] if binding else _basic_project_name(project_id)
    project_path = (
        Path(binding["basic_path"])
        if binding
        else archive_project_path(_svc.config, project_id)
    )
    project_path.mkdir(parents=True, exist_ok=True)
    _svc.projects.bind_basic_project(
        project_id,
        external_id=basic_name,
        name=basic_name,
        path=project_path,
    )

    manager = ConfigManager()
    config = manager.config
    current_name, current_path = manager.get_project(basic_name)
    if current_name is None or Path(current_path).resolve() != project_path.resolve():
        config.projects[basic_name] = ProjectEntry(path=str(project_path))
        manager.save_config(config)
        await initialize_app(config)
        current_name, _ = manager.get_project(basic_name)
    return current_name or basic_name


async def _record_created_basic_project(arguments: dict, result) -> None:
    if _svc is None:
        raise RuntimeError("MemoryService not initialised")
    project_name = str(arguments["project_name"])
    project_path = Path(str(arguments["project_path"])).expanduser().resolve()
    external_id = project_name
    if isinstance(result, dict):
        project_name = str(result.get("name") or project_name)
        project_path = Path(str(result.get("path") or project_path)).expanduser().resolve()
        external_id = str(result.get("external_id") or project_name)

    resolved = _svc.projects.resolve_workspace(project_path)
    _svc.projects.bind_basic_project(
        resolved["project_id"],
        external_id=external_id,
        name=project_name,
        path=project_path,
    )
    if arguments.get("set_default"):
        _svc.set_space(resolved["project_id"])


async def _remove_basic_project(binding: dict) -> None:
    from basic_memory.mcp.async_client import get_client
    from basic_memory.mcp.clients import ProjectClient

    async with get_client() as client:
        projects = ProjectClient(client)
        project_list = await projects.list_projects()
        external_id = binding.get("basic_external_id")
        name = binding.get("basic_name")
        path = binding.get("basic_path")
        target = next(
            (
                item
                for item in project_list.projects
                if (external_id and item.external_id == external_id)
                or (name and item.name == name)
                or (path and Path(item.path).resolve() == Path(path).resolve())
            ),
            None,
        )
        if target is None:
            return
        if target.is_default:
            replacement = next(
                (
                    item
                    for item in project_list.projects
                    if item.external_id != target.external_id
                ),
                None,
            )
            if replacement is None:
                from basic_memory import db as basic_db
                from basic_memory.config import ConfigManager
                from basic_memory.repository.project_repository import ProjectRepository

                manager = ConfigManager()
                config = manager.config
                config.projects.pop(target.name, None)
                config.default_project = None
                manager.save_config(config)
                _, session_maker = await basic_db.get_or_create_db(
                    config.app_database_path, config=config
                )
                await ProjectRepository(session_maker).delete(target.id)
                return
            await projects.set_default(replacement.external_id)
        await projects.delete_project(target.external_id, delete_notes=False)


def _local_basic_tool(fn):
    signature = inspect.signature(fn)

    @wraps(fn)
    async def invoke(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        arguments = bound.arguments
        workspace = arguments.get("workspace")
        if workspace is not None and str(workspace).strip():
            error = tool_error_response(
                tool=fn.__name__,
                engine="basic-memory",
                code="CLOUD_DISABLED",
                message="cloud workspaces are disabled in the local EverMind runtime",
                hint="Omit workspace and use a local unified project identifier.",
            )
            raise ToolError(json.dumps(error, ensure_ascii=False))

        identifiers = [
            str(arguments[key])
            for key in ("project", "project_id")
            if arguments.get(key) is not None and str(arguments[key]).strip()
        ]
        if identifiers:
            try:
                names = [await _ensure_basic_project(value) for value in identifiers]
            except ValueError as exc:
                error = tool_error_response(
                    tool=fn.__name__,
                    engine="basic-memory",
                    code="PROJECT_RESOLUTION_ERROR",
                    message=str(exc),
                    hint="Use a stable project ID, canonical path, or unambiguous display name.",
                )
                raise ToolError(json.dumps(error, ensure_ascii=False)) from exc
            if len(set(names)) != 1:
                error = tool_error_response(
                    tool=fn.__name__,
                    engine="basic-memory",
                    code="PROJECT_RESOLUTION_ERROR",
                    message="project and project_id resolve to different unified projects",
                    hint="Pass one project identifier or two aliases for the same project.",
                )
                raise ToolError(json.dumps(error, ensure_ascii=False))
            if "project" in signature.parameters:
                arguments["project"] = names[0]
            if "project_id" in signature.parameters:
                arguments["project_id"] = None

        result = fn(*bound.args, **bound.kwargs)
        result = await result if inspect.isawaitable(result) else result
        if fn.__name__ == "create_memory_project":
            await _record_created_basic_project(arguments, result)
        return result

    return invoke


async def _project_info_resource(
    project: str | None = None, context: Context | None = None
) -> str:
    if project:
        project = await _ensure_basic_project(project)
    result = await project_info(project=project, context=context)
    return result.model_dump_json()


@asynccontextmanager
async def _lifespan(_app: FastMCP):
    from basic_memory import db as basic_db
    from basic_memory.config import BasicMemoryConfig, ConfigManager, ProjectEntry
    from basic_memory.mcp.container import McpContainer, set_container
    from basic_memory.runtime import RuntimeMode
    from basic_memory.services.initialization import initialize_app

    from .config_v2 import load_config

    global _svc
    _svc = MemoryService(load_config())
    coordinator = None
    try:
        os.environ["BASIC_MEMORY_CONFIG_DIR"] = str(
            _svc.config.home / "basic-memory"
        )
        os.environ["BASIC_MEMORY_FORCE_LOCAL"] = "true"
        os.environ["BASIC_MEMORY_FORCE_CLOUD"] = "false"
        os.environ["BASIC_MEMORY_CLOUD_MODE"] = "false"
        os.environ.pop("BASIC_MEMORY_CLOUD_API_KEY", None)
        os.environ.pop("BASIC_MEMORY_DEFAULT_WORKSPACE", None)

        rows = _svc.storage.conn.execute(
            """
            SELECT project.project_id, project.display_name,
                   binding.basic_external_id, binding.basic_name, binding.basic_path
            FROM projects project
            LEFT JOIN basic_project_bindings binding
              ON binding.project_id=project.project_id
            WHERE project.state='active'
            """
        ).fetchall()
        projects = {}
        for row in rows:
            project_id = row["project_id"]
            basic_name = row["basic_name"] or _basic_project_name(project_id)
            project_path = (
                Path(row["basic_path"])
                if row["basic_path"]
                else archive_project_path(_svc.config, project_id)
            )
            project_path.mkdir(parents=True, exist_ok=True)
            projects[basic_name] = ProjectEntry(path=str(project_path))
            _svc.projects.bind_basic_project(
                project_id,
                external_id=row["basic_external_id"] or basic_name,
                name=basic_name,
                path=project_path,
            )

        basic_config = BasicMemoryConfig(
            env="user",
            projects=projects,
            default_project=_basic_project_name(_svc.space),
            semantic_search_enabled=False,
            auto_update=False,
            cloud_api_key=None,
            default_workspace=None,
            logfire_enabled=False,
            logfire_send_to_logfire=False,
        )
        ConfigManager().save_config(basic_config)
        container = McpContainer(config=basic_config, mode=RuntimeMode.LOCAL)
        set_container(container)
        await initialize_app(basic_config)
        coordinator = container.create_sync_coordinator()
        await coordinator.start()
        yield
    finally:
        if coordinator is not None:
            await coordinator.stop()
        await basic_db.shutdown_db()
        _svc.close()
        _svc = None


mcp = FastMCP(name="EverMind", lifespan=_lifespan)
for fast_tool in FAST_CORE_TOOLS:
    mcp.add_tool(_fast_core_tool(fast_tool))
for basic_tool in BASIC_TOOL_FUNCTIONS:
    mcp.add_tool(_local_basic_tool(basic_tool))

mcp.prompt(
    name="continue_conversation", description="Continue a previous conversation"
)(continue_conversation)
mcp.prompt(
    name="recent_activity",
    description="Get recent activity from a specific project or across all projects",
)(recent_activity_prompt)
mcp.prompt(
    name="search_knowledge_base",
    description="Search across all content in basic-memory",
)(search_prompt)
mcp.resource(
    uri="memory://ai_assistant_guide",
    name="ai assistant guide",
    description="Give an AI assistant guidance on how to use Basic Memory tools effectively",
)(ai_assistant_guide)
mcp.resource(
    uri="memory://{project}/info",
    description="Get information and statistics about the current Basic Memory project.",
)(_project_info_resource)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


async def main() -> None:
    await mcp.run_async(transport="stdio", show_banner=False)


def main_sync() -> None:
    import asyncio

    asyncio.run(main())


async def _maybe_update_space_from_roots(context: Context | None = None) -> None:
    """Use MCP client roots for project-space detection when available."""
    global _last_roots_space
    if _svc is None:
        return
    if os.environ.get("EVERMIND_DEFAULT_SPACE"):
        return
    if context is None:
        return
    try:
        roots = await context.list_roots()
    except Exception:
        return
    if not roots:
        return
    root_path = _root_uri_to_path(str(roots[0].uri))
    if not root_path:
        return
    try:
        resolved = _svc.projects.resolve_workspace(root_path)
    except (OSError, ValueError):
        return
    project_id = resolved["project_id"]
    if project_id != _last_roots_space:
        _svc.set_space(project_id)
        _svc.workspace_id = resolved["workspace_id"]
        _last_roots_space = project_id


def _root_uri_to_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme and parsed.scheme != "file":
        return None
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if (
            os.name == "nt"
            and path.startswith("/")
            and len(path) > 2
            and path[2] == ":"
        ):
            path = path[1:]
        return Path(path)
    return Path(uri)
