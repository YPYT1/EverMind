"""Local-first embedding profiles with optional external enhancement."""

from __future__ import annotations

import hashlib
import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .api_client import ApiMetrics, ApiResult, endpoint, post_json

logger = logging.getLogger(__name__)

LOCAL_MODEL_ID = "intfloat/multilingual-e5-small"
LOCAL_MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
LOCAL_DIMENSIONS = 384
LOCAL_QUERY_PREFIX = "query: "
LOCAL_DOCUMENT_PREFIX = "passage: "
LOCAL_MODEL_WEIGHT_BYTES = 470_641_600


def _profile_id(provider: str, model: str, version: str, dimensions: int) -> str:
    value = f"{provider}\0{model}\0{version}\0{dimensions}"
    return f"{provider}-{hashlib.sha256(value.encode()).hexdigest()[:16]}"


@dataclass(frozen=True)
class EmbeddingProfile:
    profile_id: str
    provider: str
    model: str
    version: str
    dimensions: int


@dataclass(frozen=True)
class EncodedEmbedding:
    vector: list[float]
    profile: EmbeddingProfile
    fallback_reason: str | None = None


class EmbeddingManager:
    """Generate a mandatory local vector and optional external vectors."""

    _shared_models: dict[str, object] = {}
    _shared_model_lock = threading.Lock()

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-Embedding-8B",
        enabled: bool = True,
        provider: str = "auto",
        api_key: str = "",
        api_base_url: str = "https://api.siliconflow.cn/v1",
        dimensions: int = 512,
        timeout_seconds: float = 30.0,
        queue_max_retries: int = 5,
        local_model_path: str | Path | None = None,
        local_model_name: str = LOCAL_MODEL_ID,
        local_model_revision: str = LOCAL_MODEL_REVISION,
        local_dimensions: int = LOCAL_DIMENSIONS,
        query_prefix: str = LOCAL_QUERY_PREFIX,
        document_prefix: str = LOCAL_DOCUMENT_PREFIX,
    ) -> None:
        self._model_name = model_name
        self._enabled = enabled
        self._provider = provider
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._queue_max_retries = queue_max_retries
        self._local_model_path = Path(local_model_path or self._default_model_path())
        self._query_prefix = query_prefix
        self._document_prefix = document_prefix
        self.local_profile = EmbeddingProfile(
            profile_id=_profile_id(
                "local", local_model_name, local_model_revision, local_dimensions
            ),
            provider="local",
            model=local_model_name,
            version=local_model_revision,
            dimensions=local_dimensions,
        )
        self.external_profile = (
            EmbeddingProfile(
                profile_id=_profile_id(
                    "siliconflow", model_name, "configured", dimensions
                ),
                provider="siliconflow",
                model=model_name,
                version="configured",
                dimensions=dimensions,
            )
            if self._external_configured
            else None
        )
        self._queue: queue.Queue = queue.Queue(maxsize=500)
        self._stop_event = threading.Event()
        self._on_embed: Optional[
            Callable[[str, EmbeddingProfile, list[float]], None]
        ] = None
        self._processed_count = 0
        self._failed_count = 0
        self._metrics = ApiMetrics("embedding_api")
        self._external_failures = 0
        self._external_open_until = 0.0
        self._last_selected_profile: str | None = None
        self._last_fallback_reason: str | None = None
        self._last_latency_ms: float | None = None
        self._worker = threading.Thread(
            target=self._process_queue, daemon=True, name="evermind-embed"
        )
        self._worker.start()

    @staticmethod
    def _default_model_path() -> Path:
        return (
            Path(__file__).resolve().parents[3]
            / "third_party"
            / "models"
            / "multilingual-e5-small"
        )

    @property
    def _external_configured(self) -> bool:
        return (
            self._enabled
            and self._provider in {"auto", "siliconflow"}
            and bool(self._api_key)
        )

    @property
    def profiles(self) -> tuple[EmbeddingProfile, ...]:
        if not self._enabled:
            return ()
        if self.external_profile is not None:
            return (self.local_profile, self.external_profile)
        return (self.local_profile,)

    def set_callback(
        self, fn: Callable[[str, EmbeddingProfile, list[float]], None]
    ) -> None:
        self._on_embed = fn

    def encode_query(self, text: str) -> EncodedEmbedding | None:
        started = time.perf_counter()
        fallback_reason = None
        if self.external_profile is not None:
            vector, fallback_reason = self._try_external(text)
            if vector is not None:
                return self._encoded(
                    vector, self.external_profile, None, started
                )

        vector = self._encode_local(text, query=True)
        if vector is None:
            self._record_selection(None, fallback_reason or "local_unavailable", started)
            return None
        return self._encoded(vector, self.local_profile, fallback_reason, started)

    def encode_local_query(self, text: str) -> EncodedEmbedding | None:
        started = time.perf_counter()
        vector = self._encode_local(text, query=True)
        if vector is None:
            self._record_selection(None, "local_unavailable", started)
            return None
        return self._encoded(vector, self.local_profile, None, started)

    def encode(self, text: str) -> Optional[list[float]]:
        encoded = self.encode_query(text)
        return encoded.vector if encoded is not None else None

    def enqueue(
        self, memory_id: str, text: str, profile_id: str | None = None
    ) -> None:
        if not self._enabled:
            return
        profiles = [
            profile
            for profile in self.profiles
            if profile_id is None or profile.profile_id == profile_id
        ]
        for profile in profiles:
            try:
                self._queue.put_nowait((memory_id, text, profile, 0))
            except queue.Full:
                logger.debug("Embedding queue full; skipping %s", memory_id)
                self._failed_count += 1

    @property
    def available(self) -> bool:
        return self._enabled and (
            self._local_model_available or self.external_profile is not None
        )

    @property
    def _local_model_available(self) -> bool:
        weights = self._local_model_path / "model.safetensors"
        try:
            return (
                self._local_model_path.is_dir()
                and (self._local_model_path / "config.json").is_file()
                and weights.is_file()
                and weights.stat().st_size == LOCAL_MODEL_WEIGHT_BYTES
            )
        except OSError:
            return False

    @property
    def dim(self) -> int:
        if self.external_profile is not None:
            return self.external_profile.dimensions
        return self.local_profile.dimensions

    @property
    def provider(self) -> str:
        if self._last_selected_profile == self.local_profile.profile_id:
            return "local"
        if self.external_profile is not None:
            return "siliconflow"
        return "local"

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def processed_count(self) -> int:
        return self._processed_count

    @property
    def failed_count(self) -> int:
        return self._failed_count

    @property
    def last_selected_profile(self) -> str | None:
        return self._last_selected_profile

    @property
    def last_fallback_reason(self) -> str | None:
        return self._last_fallback_reason

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms

    def metrics_snapshot(self) -> dict:
        metrics = self._metrics.snapshot()
        metrics.update(
            {
                "selected_profile": self._last_selected_profile,
                "fallback_reason": self._last_fallback_reason,
                "last_latency_ms": self._last_latency_ms,
                "local_available": self._local_model_available,
                "external_configured": self.external_profile is not None,
            }
        )
        return metrics

    def warmup(self) -> bool:
        return self.encode_local_query("warmup") is not None

    def close(self) -> None:
        if not self._stop_event.is_set():
            self._stop_event.set()
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
        self._worker.join(timeout=self._timeout_seconds + 1.0)
        self._on_embed = None

    def _encoded(
        self,
        vector: list[float],
        profile: EmbeddingProfile,
        fallback_reason: str | None,
        started: float,
    ) -> EncodedEmbedding | None:
        if len(vector) != profile.dimensions:
            logger.warning(
                "Embedding dimension mismatch for %s: expected=%d actual=%d",
                profile.profile_id,
                profile.dimensions,
                len(vector),
            )
            return None
        self._record_selection(profile.profile_id, fallback_reason, started)
        return EncodedEmbedding(vector, profile, fallback_reason)

    def _record_selection(
        self, profile_id: str | None, fallback_reason: str | None, started: float
    ) -> None:
        self._last_selected_profile = profile_id
        self._last_fallback_reason = fallback_reason
        self._last_latency_ms = round((time.perf_counter() - started) * 1000, 3)

    def _try_external(self, text: str) -> tuple[list[float] | None, str | None]:
        if self.external_profile is None:
            return None, "external_unavailable"
        if time.monotonic() < self._external_open_until:
            return None, "circuit_open"
        vector = self._encode_api(text)
        if vector is not None and len(vector) == self.external_profile.dimensions:
            self._external_failures = 0
            return vector, None
        self._external_failures += 1
        if self._external_failures >= 3:
            self._external_open_until = time.monotonic() + 30.0
        return None, "external_unavailable"

    def _encode_api(self, text: str) -> Optional[list[float]]:
        if not self._api_key:
            return None
        payload = {
            "model": self._model_name,
            "input": text,
            "encoding_format": "float",
            "dimensions": self._dimensions,
        }
        data = post_json(
            url=endpoint(self._api_base_url, "/embeddings"),
            api_key=self._api_key,
            payload=payload,
            timeout=self._timeout_seconds,
            purpose="Embedding",
        )
        self._metrics.record(data)
        if not data.ok:
            return None
        try:
            embedding = data.data["data"][0]["embedding"] if data.data else None
            if isinstance(embedding, list):
                return [float(value) for value in embedding]
        except Exception:
            logger.warning("Embedding response did not contain a usable vector")
            self._metrics.record(
                ApiResult(
                    ok=False,
                    data=None,
                    latency_ms=0.0,
                    error_type="parse_error",
                    error_message="embedding vector missing",
                )
            )
        return None

    def _encode_local(self, text: str, *, query: bool) -> Optional[list[float]]:
        model = self._get_local_model()
        if model is None:
            return None
        prefix = self._query_prefix if query else self._document_prefix
        try:
            vector = model.encode(
                prefix + text,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return vector.tolist()
        except Exception as exc:
            logger.warning("Local embedding encode failed: %s", exc)
            return None

    def _get_local_model(self):
        if not self._enabled or not self._local_model_available:
            return None
        key = str(self._local_model_path.resolve())
        cached = self._shared_models.get(key)
        if cached is not None:
            return cached
        with self._shared_model_lock:
            cached = self._shared_models.get(key)
            if cached is not None:
                return cached
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                logger.info("Loading bundled embedding model: %s", key)
                model = SentenceTransformer(key, local_files_only=True)
                self._shared_models[key] = model
                return model
            except ImportError:
                logger.error("sentence-transformers is required for local embeddings")
            except Exception as exc:
                logger.error("Failed to load bundled embedding model: %s", exc)
            return None

    def _process_queue(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=1.0)
                if item is None:
                    self._queue.task_done()
                    break
                memory_id, text, profile, attempt = item
                if profile.provider == "local":
                    vector = self._encode_local(text, query=False)
                else:
                    vector, _ = self._try_external(text)
                if vector is not None and len(vector) == profile.dimensions:
                    if self._on_embed is not None:
                        self._on_embed(memory_id, profile, vector)
                    self._processed_count += 1
                elif attempt < self._queue_max_retries and self._enabled:
                    if self._stop_event.wait(min(2**attempt, 5)):
                        self._queue.task_done()
                        break
                    try:
                        self._queue.put_nowait((memory_id, text, profile, attempt + 1))
                    except queue.Full:
                        self._failed_count += 1
                else:
                    self._failed_count += 1
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                logger.debug("Embed worker error: %s", exc)

    def cosine_similarity(self, vec1: list, vec2: list) -> float:
        try:
            if not vec1 or not vec2 or len(vec1) != len(vec2):
                return 0.0
            dot = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(b * b for b in vec2) ** 0.5
            if norm1 == 0.0 or norm2 == 0.0:
                return 0.0
            return dot / (norm1 * norm2)
        except Exception:
            return 0.0
