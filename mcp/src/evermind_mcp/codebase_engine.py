"""EverMind internal code graph engine."""
from __future__ import annotations

from dataclasses import dataclass

from .config_v2 import EverMindConfig
from .native_codebase import NativeCodebase
from .tool_bridge import bridge_error_response
from .vendored_codebase import VendoredCodebase


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

    def call(self, tool: str, arguments: dict | None = None) -> dict:
        if tool not in CODEBASE_TOOL_NAMES:
            return bridge_error_response(
                tool=tool,
                engine="evermind-code-graph",
                code="CODEBASE_UNKNOWN_TOOL",
                message=f"unknown codebase tool: {tool}",
            )

        vendored = VendoredCodebase(self.config)
        if vendored.available:
            return vendored.call(tool, arguments or {})

        result = NativeCodebase(self.config).call(tool, arguments or {})
        result["fallback"] = "native"
        result["vendored_backend"] = vendored.metadata()
        return result

    def metadata(self) -> dict:
        vendored = VendoredCodebase(self.config)
        metadata = vendored.metadata()
        metadata["active_backend"] = (
            "vendored-codebase-memory-mcp" if vendored.available else "native-python"
        )
        return metadata
