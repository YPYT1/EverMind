"""
EverMind MCP Server v2 — 4-tool interface.

Tools: remember, recall, forget, briefing
"""

from __future__ import annotations

import json
import logging

from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp import types
import mcp.server.stdio

from .memory_service_v2 import MemoryService

logger = logging.getLogger(__name__)

server = Server("evermind-mcp")

_svc: MemoryService | None = None

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
            "mode (hybrid/fts/semantic)."
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

        if name == "remember":
            result = await _svc.remember(
                content=args["content"],
                importance=args.get("importance", 0),
                tags=args.get("tags", []),
                memory_type=args.get("memory_type", "auto"),
            )

        elif name == "recall":
            result = await _svc.recall(
                query=args["query"],
                limit=args.get("limit", 10),
                mode=args.get("mode", "hybrid"),
            )

        elif name == "forget":
            result = await _svc.forget(id=args["id"])

        elif name == "briefing":
            result = await _svc.briefing()

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
