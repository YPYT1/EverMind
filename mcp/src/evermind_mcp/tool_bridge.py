"""Backward-compatible wrapper for EverMind tool error envelopes."""
from __future__ import annotations

from collections.abc import Sequence

from .tool_errors import tool_error_response


def bridge_error_response(
    *,
    tool: str,
    engine: str,
    code: str,
    message: str,
    hint: str = "",
    retryable: bool = False,
    latency_ms: float | None = None,
    returncode: int | None = None,
    command: Sequence[str] | None = None,
    stdout: str = "",
    stderr: str = "",
) -> dict:
    """Compatibility alias for older imports."""
    return tool_error_response(
        tool=tool,
        engine=engine,
        code=code,
        message=message,
        hint=hint,
        retryable=retryable,
        latency_ms=latency_ms,
        returncode=returncode,
        command=command,
        stdout=stdout,
        stderr=stderr,
    )
