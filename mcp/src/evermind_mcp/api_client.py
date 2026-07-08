"""Small OpenAI-compatible HTTP helpers used by optional model managers."""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib import error, request

logger = logging.getLogger(__name__)


@dataclass
class ApiResult:
    ok: bool
    data: dict[str, Any] | None
    latency_ms: float
    status_code: int | None = None
    error_type: str | None = None
    error_message: str | None = None


class ApiMetrics:
    """Small rolling metrics collector for optional external model APIs."""

    def __init__(self, name: str, window_size: int = 200) -> None:
        self._name = name
        self._latencies: deque[float] = deque(maxlen=window_size)
        self._success_count = 0
        self._failure_count = 0
        self._timeout_count = 0
        self._http_error_count = 0
        self._parse_error_count = 0
        self._network_error_count = 0
        self._unexpected_error_count = 0
        self._last_latency_ms: float | None = None
        self._last_error_type: str | None = None
        self._last_error_message: str | None = None
        self._last_status_code: int | None = None
        self._lock = threading.Lock()

    def record(self, result: ApiResult) -> None:
        with self._lock:
            self._latencies.append(result.latency_ms)
            self._last_latency_ms = result.latency_ms
            self._last_status_code = result.status_code
            if result.ok:
                self._success_count += 1
                self._last_error_type = None
                self._last_error_message = None
                return

            self._failure_count += 1
            self._last_error_type = result.error_type
            self._last_error_message = result.error_message
            if result.error_type == "timeout":
                self._timeout_count += 1
            elif result.error_type == "http_error":
                self._http_error_count += 1
            elif result.error_type == "parse_error":
                self._parse_error_count += 1
            elif result.error_type == "network_error":
                self._network_error_count += 1
            else:
                self._unexpected_error_count += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            latencies = list(self._latencies)
            return {
                "name": self._name,
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "timeout_count": self._timeout_count,
                "http_error_count": self._http_error_count,
                "parse_error_count": self._parse_error_count,
                "network_error_count": self._network_error_count,
                "unexpected_error_count": self._unexpected_error_count,
                "recent_count": len(latencies),
                "last_latency_ms": self._last_latency_ms,
                "latency_p50_ms": _percentile(latencies, 0.50),
                "latency_p95_ms": _percentile(latencies, 0.95),
                "last_status_code": self._last_status_code,
                "last_error_type": self._last_error_type,
                "last_error_message": self._last_error_message,
            }


def endpoint(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    return base + suffix


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * quantile)
    return round(ordered[index], 3)


def _safe_error_message(exc: Exception, limit: int = 200) -> str:
    message = str(exc).replace("\n", " ").strip()
    return message[:limit]


def post_json(
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: float,
    purpose: str,
) -> ApiResult:
    started = time.perf_counter()
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - user-configured API endpoint
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError as exc:
                latency_ms = round((time.perf_counter() - started) * 1000, 3)
                logger.warning("%s response parse failed: %s", purpose, exc)
                return ApiResult(
                    ok=False,
                    data=None,
                    latency_ms=latency_ms,
                    status_code=getattr(resp, "status", None),
                    error_type="parse_error",
                    error_message=_safe_error_message(exc),
                )
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            return ApiResult(
                ok=True,
                data=parsed,
                latency_ms=latency_ms,
                status_code=getattr(resp, "status", None),
            )
    except error.HTTPError as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.warning("%s request failed: HTTP %s", purpose, exc.code)
        return ApiResult(
            ok=False,
            data=None,
            latency_ms=latency_ms,
            status_code=exc.code,
            error_type="http_error",
            error_message=f"HTTP {exc.code}",
        )
    except (TimeoutError, socket.timeout) as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.warning("%s request timed out after %.2fs", purpose, timeout)
        return ApiResult(
            ok=False,
            data=None,
            latency_ms=latency_ms,
            error_type="timeout",
            error_message=_safe_error_message(exc) or f"timeout after {timeout}s",
        )
    except error.URLError as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower():
            error_type = "timeout"
            logger.warning("%s request timed out after %.2fs", purpose, timeout)
        else:
            error_type = "network_error"
            logger.warning("%s request failed: %s", purpose, reason)
        return ApiResult(
            ok=False,
            data=None,
            latency_ms=latency_ms,
            error_type=error_type,
            error_message=_safe_error_message(exc),
        )
    except OSError as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        error_type = "timeout" if "timed out" in str(exc).lower() else "network_error"
        logger.warning("%s request failed: %s", purpose, exc)
        return ApiResult(
            ok=False,
            data=None,
            latency_ms=latency_ms,
            error_type=error_type,
            error_message=_safe_error_message(exc),
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.warning("%s request failed: %s", purpose, exc)
        return ApiResult(
            ok=False,
            data=None,
            latency_ms=latency_ms,
            error_type="unexpected_error",
            error_message=_safe_error_message(exc),
        )
