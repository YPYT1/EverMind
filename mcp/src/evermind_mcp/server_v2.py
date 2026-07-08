"""
EverMind MCP Server v2 — 13-tool interface.

Tools: remember, recall, forget, briefing, list, graph_explore, status,
export, compact, tags, reindex, health, list_spaces
"""

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

logger = logging.getLogger(__name__)

server = Server("evermind-mcp")

_svc: MemoryService | None = None
_last_roots_space: str | None = None

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS: list[types.Tool] = [
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
            },
            "required": ["content"],
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
            "properties": {},
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
            )

        elif name == "forget":
            result = await _svc.forget(memory_id=args["id"])

        elif name == "briefing":
            result = await _svc.briefing()

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

        else:
            result = {"error": f"Unknown tool: {name}", "tool": name}

    except Exception as exc:
        logger.exception("Tool %s failed", name)
        result = {"error": str(exc), "tool": name}

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
