"""EverMind MCP Server v2 — unified memory, code graph, and archive interface."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp import types
import mcp.server.stdio

from .memory_service_v2 import MemoryService
from .project_detector import detect_project_space
from .archive_bridge import ARCHIVE_TOOL_NAMES
from .codebase_engine import CODEBASE_TOOL_NAMES
from .tool_bridge import bridge_error_response

logger = logging.getLogger(__name__)

server = Server("evermind-mcp")

_svc: MemoryService | None = None
_last_roots_space: str | None = None

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

def _props(*names: str) -> dict:
    schema = {
        "query": {"type": "string"},
        "identifier": {"type": "string"},
        "title": {"type": "string"},
        "folder": {"type": "string"},
        "content": {"type": "string"},
        "project": {"type": "string"},
        "project_id": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "type": {
            "oneOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
            ]
        },
        "overwrite": {"type": "boolean", "default": False},
        "local": {"type": "boolean", "default": False},
        "cloud": {"type": "boolean", "default": False},
        "include_frontmatter": {"type": "boolean", "default": False},
        "is_directory": {"type": "boolean", "default": False},
        "operation": {"type": "string"},
        "find_text": {"type": "string"},
        "section": {"type": "string"},
        "expected_replacements": {"type": "integer"},
        "url": {"type": "string"},
        "depth": {"type": "integer"},
        "timeframe": {"type": "string"},
        "page": {"type": "integer"},
        "page_size": {"type": "integer"},
        "max_related": {"type": "integer"},
        "permalink": {"type": "boolean", "default": False},
        "vector": {"type": "boolean", "default": False},
        "hybrid": {"type": "boolean", "default": False},
        "after_date": {"type": "string"},
        "status": {"type": "string"},
        "entity_type": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "array", "items": {"type": "string"}},
        "meta": {"type": "array", "items": {"type": "string"}},
        "filter": {"type": "string"},
        "target": {"type": "string"},
        "note_type": {"type": "string"},
        "threshold": {"type": "number"},
        "project_slug": {"type": "string"},
        "target_file": {"type": "string"},
        "evidence": {"type": "string"},
        "reason": {"type": "string"},
        "candidate_id": {"type": "string"},
        "confirmed": {"type": "boolean", "default": False},
    }
    return {name: schema[name] for name in names}


def _tool(name: str, schema: dict) -> types.Tool:
    return types.Tool(
        name=name,
        description=schema["description"],
        inputSchema={
            "type": "object",
            "properties": schema["properties"],
            "required": schema.get("required", []),
        },
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
                    "enum": ["auto", "episodic", "semantic", "procedural", "decision", "bug", "preference"],
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
            "or needs verified metadata/tags without deleting and recreating it. Rebuilds "
            "FTS, embeddings, graph links, and briefing cache as needed."
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
                    "enum": ["auto", "episodic", "semantic", "procedural", "decision", "bug", "preference"],
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
                    "enum": ["working", "episodic", "semantic", "procedural", "archive"],
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
                    "enum": ["working", "episodic", "semantic", "procedural", "archive"],
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
                    "enum": ["working", "episodic", "semantic", "procedural", "archive"],
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
        "description": "Index a repository into the Codebase Memory graph engine.",
        "properties": {
            "repo_path": {"type": "string", "description": "Absolute repository path"},
            "project": {"type": "string", "description": "Optional explicit project name"},
        },
        "required": ["repo_path"],
    },
    "list_projects": {
        "description": "List all indexed Codebase Memory projects.",
        "properties": {},
        "required": [],
    },
    "delete_project": {
        "description": "Delete an indexed Codebase Memory project.",
        "properties": {"project": {"type": "string"}},
        "required": ["project"],
    },
    "index_status": {
        "description": "Get Codebase Memory indexing status for a project.",
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

ARCHIVE_TOOL_SCHEMAS: dict[str, dict] = {
    "write_note": {
        "description": "Create or overwrite a Basic Memory Markdown note.",
        "properties": _props("title", "folder", "content", "project", "project_id", "tags", "type", "overwrite", "local", "cloud"),
        "required": ["title", "folder"],
    },
    "read_note": {
        "description": "Read a Basic Memory note by identifier or memory:// URL.",
        "properties": _props("identifier", "project", "project_id", "include_frontmatter", "local", "cloud"),
        "required": ["identifier"],
    },
    "delete_note": {
        "description": "Delete a Basic Memory note or directory.",
        "properties": _props("identifier", "project", "project_id", "is_directory", "local", "cloud"),
        "required": ["identifier"],
    },
    "edit_note": {
        "description": "Edit a Basic Memory note via append/prepend/find_replace/replace_section.",
        "properties": _props("identifier", "operation", "content", "find_text", "section", "expected_replacements", "project", "project_id", "local", "cloud"),
        "required": ["identifier", "operation", "content"],
    },
    "build_context": {
        "description": "Build related Basic Memory context from a note URL.",
        "properties": _props("url", "depth", "timeframe", "page", "page_size", "max_related", "project", "project_id", "local", "cloud"),
        "required": ["url"],
    },
    "recent_activity": {
        "description": "Return recent Basic Memory activity.",
        "properties": _props("type", "depth", "timeframe", "page", "page_size", "project", "project_id", "local", "cloud"),
        "required": [],
    },
    "search_notes": {
        "description": "Search Basic Memory notes.",
        "properties": _props("query", "permalink", "title", "vector", "hybrid", "after_date", "tags", "status", "type", "entity_type", "category", "meta", "filter", "page", "page_size", "project", "project_id", "local", "cloud"),
        "required": [],
    },
    "list_memory_projects": {
        "description": "List Basic Memory projects.",
        "properties": _props("local", "cloud"),
        "required": [],
    },
    "list_workspaces": {
        "description": "List Basic Memory cloud workspaces.",
        "properties": _props("local", "cloud"),
        "required": [],
    },
    "schema_validate": {
        "description": "Validate Basic Memory notes against schemas.",
        "properties": _props("target", "project", "project_id", "local", "cloud"),
        "required": [],
    },
    "schema_infer": {
        "description": "Infer a Basic Memory schema from notes of a type.",
        "properties": _props("note_type", "threshold", "project", "project_id", "local", "cloud"),
        "required": ["note_type"],
    },
    "schema_diff": {
        "description": "Show Basic Memory schema drift for a note type.",
        "properties": _props("note_type", "project", "project_id", "local", "cloud"),
        "required": ["note_type"],
    },
    "propose_basic_memory_update": {
        "description": "Write a reviewed Basic Memory candidate; does not modify formal notes.",
        "properties": _props("project_slug", "target_file", "content", "evidence", "reason"),
        "required": ["project_slug", "target_file", "content"],
    },
    "commit_basic_memory_update": {
        "description": "Commit a Basic Memory candidate only when confirmed=true.",
        "properties": _props("candidate_id", "confirmed"),
        "required": ["candidate_id", "confirmed"],
    },
}

TOOLS: list[types.Tool] = [
    *MEMORY_TOOLS,
    *[_tool(name, CODEBASE_TOOL_SCHEMAS[name]) for name in sorted(CODEBASE_TOOL_NAMES)],
    *[_tool(name, ARCHIVE_TOOL_SCHEMAS[name]) for name in sorted(ARCHIVE_TOOL_NAMES)],
]

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    args = arguments or {}

    try:
        if _svc is None:
            raise RuntimeError("MemoryService not initialised")

        await _maybe_update_space_from_roots()

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

        elif name in CODEBASE_TOOL_NAMES:
            result = _svc.codebase.call(name, args)

        elif name in ARCHIVE_TOOL_NAMES:
            result = _svc.archive.call(name, args)

        else:
            result = {"error": f"Unknown tool: {name}", "tool": name}

    except KeyError as exc:
        missing = str(exc.args[0])
        result = bridge_error_response(
            tool=name,
            engine="evermind-mcp",
            code="MCP_INVALID_ARGUMENT",
            message=f"missing required argument: {missing}",
            hint="Check the tool input schema and provide all required arguments.",
        )

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        result = bridge_error_response(
            tool=name,
            engine="evermind-mcp",
            code="MCP_TOOL_EXCEPTION",
            message=str(exc),
            hint="Check the tool input schema and EverMind logs for details.",
        )

    return [
        types.TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2),
        )
    ]


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


async def main() -> None:
    from .config_v2 import load_config

    global _svc
    config = load_config()
    _svc = MemoryService(config)

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="evermind-mcp",
                server_version="2.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main_sync() -> None:
    import asyncio

    asyncio.run(main())


async def _maybe_update_space_from_roots() -> None:
    """Use MCP client roots for project-space detection when available."""
    global _last_roots_space
    if _svc is None:
        return
    if os.environ.get("EVERMIND_DEFAULT_SPACE"):
        return
    try:
        session = server.request_context.session
        client_params = session.client_params
        if (
            client_params is None
            or client_params.capabilities is None
            or client_params.capabilities.roots is None
        ):
            return
        roots_result = await session.list_roots()
    except Exception:
        return
    roots = getattr(roots_result, "roots", None) or []
    if not roots:
        return
    root_path = _root_uri_to_path(str(roots[0].uri))
    if not root_path:
        return
    space = detect_project_space(str(root_path))
    if space and space != _last_roots_space:
        _svc.set_space(space)
        _last_roots_space = space


def _root_uri_to_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme and parsed.scheme != "file":
        return None
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]
        return Path(path)
    return Path(uri)
