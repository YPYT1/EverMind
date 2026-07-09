"""Subprocess bridge for bundled external MCP engines."""
from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from shutil import which


_PYTHON_ENV_KEYS_TO_DROP = {"PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE"}


@dataclass(frozen=True)
class BridgeResult:
    ok: bool
    command: list[str]
    latency_ms: float
    returncode: int
    stdout: str
    stderr: str
    data: object | None
    error: str | None = None

    def to_dict(self) -> dict:
        result = {
            "ok": self.ok,
            "latency_ms": round(self.latency_ms, 3),
            "returncode": self.returncode,
            "data": self.data,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "command": self.command,
        }
        if self.error:
            result["error"] = self.error
        return result


def resolve_executable(configured: str, fallback: str) -> str | None:
    """Resolve a configured executable path or PATH command."""
    candidates = [configured, fallback] if configured else [fallback]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return str(path)
        found = which(candidate)
        if found:
            return found
    return None


def run_json_command(
    command: Sequence[str],
    *,
    timeout_seconds: float,
    allow_text: bool = False,
) -> BridgeResult:
    """Run a command and parse stdout as JSON when possible."""
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            encoding="utf-8",
            env=_bridge_subprocess_env(),
            errors="replace",
            timeout=timeout_seconds,
        )
        latency_ms = (time.perf_counter() - started) * 1000
    except FileNotFoundError as exc:
        return BridgeResult(
            ok=False,
            command=list(command),
            latency_ms=(time.perf_counter() - started) * 1000,
            returncode=127,
            stdout="",
            stderr="",
            data=None,
            error=f"executable not found: {exc.filename}",
        )
    except subprocess.TimeoutExpired as exc:
        return BridgeResult(
            ok=False,
            command=list(command),
            latency_ms=(time.perf_counter() - started) * 1000,
            returncode=124,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
            data=None,
            error=f"command timed out after {timeout_seconds}s",
        )

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    data: object | None = None
    parse_error: str | None = None
    if stdout:
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            if allow_text:
                data = stdout
            else:
                parse_error = f"stdout is not JSON: {exc.msg}"

    ok = completed.returncode == 0 and parse_error is None
    return BridgeResult(
        ok=ok,
        command=list(command),
        latency_ms=latency_ms,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        data=data,
        error=parse_error if completed.returncode == 0 else stderr or parse_error,
    )


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
    """Return a stable error envelope for all external bridge failures."""
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


def bridge_failure_response(
    result: BridgeResult,
    *,
    tool: str,
    engine: str,
    hint: str = "",
) -> dict:
    code = _bridge_error_code(result)
    return bridge_error_response(
        tool=tool,
        engine=engine,
        code=code,
        message=result.error or result.stderr or "bridge command failed",
        hint=hint,
        retryable=code in {"BRIDGE_TIMEOUT", "BRIDGE_TRANSIENT_FAILURE"},
        latency_ms=result.latency_ms,
        returncode=result.returncode,
        command=result.command,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _bridge_error_code(result: BridgeResult) -> str:
    if result.returncode == 124:
        return "BRIDGE_TIMEOUT"
    if result.returncode == 127:
        return "BRIDGE_EXECUTABLE_NOT_FOUND"
    if result.error and result.error.startswith("stdout is not JSON"):
        return "BRIDGE_INVALID_JSON"
    if result.returncode != 0:
        return "BRIDGE_SUBPROCESS_FAILED"
    return "BRIDGE_TRANSIENT_FAILURE"


def _bridge_subprocess_env() -> dict[str, str]:
    """Return an env safe for external Python CLI wrappers."""
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in _PYTHON_ENV_KEYS_TO_DROP
    }
