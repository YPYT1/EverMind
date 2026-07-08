"""Optional OpenAI-compatible LLM helper for briefing summaries."""
from __future__ import annotations

import logging

from .api_client import ApiMetrics, ApiResult, endpoint, post_json
from .types_v2 import MemoryRow

logger = logging.getLogger(__name__)


class LLMManager:
    def __init__(
        self,
        *,
        model_name: str = "deepseek-ai/DeepSeek-V4-Flash",
        enabled: bool = False,
        api_key: str = "",
        api_base_url: str = "https://api.siliconflow.cn/v1",
        timeout_seconds: float = 30.0,
    ) -> None:
        self._model_name = model_name
        self._enabled = enabled
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._timeout_seconds = timeout_seconds
        self._metrics = ApiMetrics("llm_api")

    @property
    def available(self) -> bool:
        return self._enabled and bool(self._api_key)

    @property
    def model_name(self) -> str:
        return self._model_name

    def metrics_snapshot(self) -> dict:
        return self._metrics.snapshot()

    def summarize_briefing(self, memories: list[MemoryRow | dict]) -> str | None:
        if not self.available or not memories:
            return None
        lines = []
        for item in memories[:8]:
            content = item.get("content") if isinstance(item, dict) else item.content
            layer = item.get("layer") if isinstance(item, dict) else item.layer
            memory_type = item.get("memory_type") or item.get("type") if isinstance(item, dict) else item.memory_type
            lines.append(f"- [{layer}/{memory_type}] {content}")
        payload = {
            "model": self._model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Summarize project memories for a coding agent. "
                        "Keep it concise, factual, and do not invent facts."
                    ),
                },
                {
                    "role": "user",
                    "content": "Project memories:\n" + "\n".join(lines),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 300,
        }
        data = post_json(
            url=endpoint(self._api_base_url, "/chat/completions"),
            api_key=self._api_key,
            payload=payload,
            timeout=self._timeout_seconds,
            purpose="LLM briefing",
        )
        self._metrics.record(data)
        if not data.ok:
            return None
        try:
            content = data.data["choices"][0]["message"]["content"] if data.data else None
            if isinstance(content, str) and content.strip():
                return content.strip()
        except Exception:
            logger.warning("LLM response did not contain a usable message")
            self._metrics.record(
                ApiResult(
                    ok=False,
                    data=None,
                    latency_ms=0.0,
                    error_type="parse_error",
                    error_message="message content missing",
                )
            )
        return None
