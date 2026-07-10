"""Shared error envelopes for EverMind tool engines."""
from __future__ import annotations

from collections.abc import Sequence


def tool_error_response(
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
    """Return a stable machine-readable error envelope for tool failures."""
    response = {
        "ok": False,
        "tool": tool,
        "engine": engine,
        "error": message,
        "code": code,
        "message": message,
        "hint": hint,
        "retryable": retryable,
    }
    if latency_ms is not None:
        response["latency_ms"] = round(latency_ms, 3)
    if returncode is not None:
        response["returncode"] = returncode
    if command is not None:
        response["command"] = list(command)
    if stdout:
        response["stdout"] = stdout
    if stderr:
        response["stderr"] = stderr
    return response
