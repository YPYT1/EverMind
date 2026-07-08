"""Optional SiliconFlow reranker for final recall ordering."""
from __future__ import annotations

import logging
from typing import Iterable

from .api_client import ApiMetrics, endpoint, post_json
from .types_v2 import MemoryRow

logger = logging.getLogger(__name__)


class RerankerManager:
    def __init__(
        self,
        *,
        model_name: str = "Qwen/Qwen3-Reranker-8B",
        enabled: bool = True,
        api_key: str = "",
        api_base_url: str = "https://api.siliconflow.cn/v1",
        timeout_seconds: float = 30.0,
        instruction: str = "",
    ) -> None:
        self._model_name = model_name
        self._enabled = enabled
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._timeout_seconds = timeout_seconds
        self._instruction = instruction
        self._last_scores: list[dict] = []
        self._last_latency_ms: float | None = None
        self._last_applied = False
        self._last_fallback_reason: str | None = None
        self._metrics = ApiMetrics("rerank_api")

    @property
    def available(self) -> bool:
        return self._enabled and bool(self._api_key)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def last_scores(self) -> list[dict]:
        return self._last_scores

    @property
    def last_applied(self) -> bool:
        return self._last_applied

    @property
    def last_fallback_reason(self) -> str | None:
        return self._last_fallback_reason

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms

    def metrics_snapshot(self) -> dict:
        return self._metrics.snapshot()

    def warmup(self) -> bool:
        if not self.available:
            return False
        dummy = MemoryRow(id="warmup", content="warmup", space="coding:warmup")
        other = MemoryRow(id="warmup-2", content="other", space="coding:warmup")
        self.rerank("warmup", [dummy, other], top_k=1)
        return self._last_applied

    def rerank(
        self,
        query: str,
        candidates: Iterable[MemoryRow],
        *,
        top_k: int,
    ) -> list[MemoryRow]:
        candidate_list = list(candidates)
        if not candidate_list:
            self._mark_fallback("no_candidates")
            return []
        if not self.available or len(candidate_list) == 1:
            reason = "unavailable" if not self.available else "single_candidate"
            self._mark_fallback(reason)
            return candidate_list[:top_k]

        documents = [m.content for m in candidate_list]
        payload = {
            "model": self._model_name,
            "query": query,
            "documents": documents,
            "top_n": min(top_k, len(candidate_list)),
            "return_documents": False,
        }
        if self._instruction:
            payload["instruction"] = self._instruction

        data = post_json(
            url=endpoint(self._api_base_url, "/rerank"),
            api_key=self._api_key,
            payload=payload,
            timeout=self._timeout_seconds,
            purpose="Rerank",
        )
        self._metrics.record(data)
        self._last_latency_ms = data.latency_ms
        if not data.ok:
            self._mark_fallback(data.error_type or "api_error")
            return candidate_list[:top_k]

        parsed = self._parse_results(data.data, candidate_list)
        if not parsed:
            self._mark_fallback("empty_or_invalid_response")
            return candidate_list[:top_k]

        ranked = []
        self._last_scores = []
        for memory, score in parsed:
            memory.score = float(score)
            ranked.append(memory)
            self._last_scores.append({"id": memory.id, "score": round(float(score), 6)})
        self._last_applied = True
        self._last_fallback_reason = None
        return ranked[:top_k]

    def _mark_fallback(self, reason: str) -> None:
        self._last_applied = False
        self._last_fallback_reason = reason
        self._last_scores = []

    @staticmethod
    def _parse_results(
        data: dict | None,
        candidates: list[MemoryRow],
    ) -> list[tuple[MemoryRow, float]]:
        if not data:
            return []
        results = data.get("results") or data.get("data") or []
        parsed: list[tuple[MemoryRow, float]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            score = (
                item.get("relevance_score")
                if item.get("relevance_score") is not None
                else item.get("score")
            )
            if index is None or score is None:
                continue
            try:
                idx = int(index)
                if 0 <= idx < len(candidates):
                    parsed.append((candidates[idx], float(score)))
            except (TypeError, ValueError):
                continue
        parsed.sort(key=lambda item: item[1], reverse=True)
        return parsed
