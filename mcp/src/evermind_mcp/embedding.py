"""Optional local embedding manager for EverMind v2.

Gracefully degrades: if sentence-transformers is not installed,
embedding is disabled and only FTS5 keyword search is used.
"""
from __future__ import annotations

import logging
import queue
import time
import threading
from typing import Optional, Callable

from .api_client import ApiMetrics, ApiResult, endpoint, post_json

logger = logging.getLogger(__name__)

_EMBED_DIM = 512  # bge-small dims; override with FLOAT[384] for MiniLM


class EmbeddingManager:
    """Lazy-loading embedding manager with background indexing queue."""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-Embedding-8B",
        enabled: bool = True,
        provider: str = "auto",
        api_key: str = "",
        api_base_url: str = "https://api.siliconflow.cn/v1",
        dimensions: int = _EMBED_DIM,
        timeout_seconds: float = 30.0,
        queue_max_retries: int = 5,
    ):
        self._model_name = model_name
        self._enabled = enabled
        self._provider = provider
        self._api_key = api_key
        self._api_base_url = api_base_url
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._queue_max_retries = queue_max_retries
        self._model = None
        self._model_lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue(maxsize=500)
        self._on_embed: Optional[Callable[[str, list[float]], None]] = None
        self._processed_count = 0
        self._failed_count = 0
        self._metrics = ApiMetrics("embedding_api")
        if self._provider == "auto" and not self._api_key and self._model_name.startswith("Qwen/"):
            self._enabled = False
        self._worker = threading.Thread(target=self._process_queue, daemon=True, name="evermind-embed")
        self._worker.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_callback(self, fn: Callable[[str, list[float]], None]) -> None:
        """Register callback called after each background embedding completes.

        fn(memory_id, embedding_vector)
        """
        self._on_embed = fn

    def encode(self, text: str) -> Optional[list[float]]:
        """Synchronously encode text. Returns None when embedding unavailable."""
        if self._use_api:
            return self._encode_api(text)

        model = self._get_model()
        if model is None:
            return None
        try:
            vec = model.encode(text, normalize_embeddings=True)
            return vec.tolist()
        except Exception as exc:
            logger.warning("Embedding encode failed: %s", exc)
            return None

    def enqueue(self, memory_id: str, text: str) -> None:
        """Schedule background embedding for a stored memory."""
        if not self._enabled:
            return
        try:
            self._queue.put_nowait((memory_id, text, 0))
        except queue.Full:
            logger.debug("Embedding queue full; skipping %s", memory_id)
            self._failed_count += 1

    @property
    def available(self) -> bool:
        if self._use_api:
            return bool(self._api_key)
        return self._get_model() is not None

    @property
    def dim(self) -> int:
        """Return embedding dimensions for schema creation."""
        if self._use_api:
            return self._dimensions
        model = self._get_model()
        if model is None:
            return 384  # default fallback
        try:
            vec = model.encode("test")
            return len(vec)
        except Exception:
            return 384

    @property
    def provider(self) -> str:
        return "siliconflow" if self._use_api else "local"

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def processed_count(self) -> int:
        return self._processed_count

    @property
    def failed_count(self) -> int:
        return self._failed_count

    def metrics_snapshot(self) -> dict:
        return self._metrics.snapshot()

    def warmup(self) -> bool:
        """Load the model or verify the API path with a tiny request."""
        return self.encode("warmup") is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @property
    def _use_api(self) -> bool:
        if not self._enabled:
            return False
        if self._provider == "siliconflow":
            return True
        if self._provider == "local":
            return False
        return bool(self._api_key)

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
                return [float(x) for x in embedding]
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

    def _get_model(self):
        if not self._enabled:
            return None
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                logger.info("Loading embedding model: %s", self._model_name)
                self._model = SentenceTransformer(self._model_name)
                logger.info("Embedding model ready (dim=%d)", self.dim)
            except ImportError:
                logger.info(
                    "sentence-transformers not installed; vector search disabled. "
                    "Install with: pip install sentence-transformers"
                )
                self._enabled = False
            except Exception as exc:
                logger.warning("Failed to load embedding model: %s", exc)
                self._enabled = False
        return self._model

    def _process_queue(self) -> None:
        """Background worker: encode queued memories and fire callback."""
        while True:
            try:
                memory_id, text, attempt = self._queue.get(timeout=1.0)
                vec = self.encode(text)
                if vec is not None and self._on_embed:
                    try:
                        self._on_emit(memory_id, vec)
                        self._processed_count += 1
                    except Exception as exc:
                        logger.debug("Embed callback error: %s", exc)
                elif vec is None:
                    if attempt < self._queue_max_retries and self._enabled:
                        time.sleep(min(2 ** attempt, 5))
                        try:
                            self._queue.put_nowait((memory_id, text, attempt + 1))
                        except queue.Full:
                            self._failed_count += 1
                    else:
                        self._failed_count += 1
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                logger.debug("Embed worker error: %s", exc)

    def _on_emit(self, memory_id: str, vec: list[float]) -> None:
        if self._on_embed:
            self._on_embed(memory_id, vec)

    def cosine_similarity(self, vec1: list, vec2: list) -> float:
        """Compute cosine similarity between two embedding vectors. Returns 0.0 on error."""
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
