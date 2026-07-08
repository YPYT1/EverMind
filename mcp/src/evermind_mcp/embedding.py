"""Optional local embedding manager for EverMind v2.

Gracefully degrades: if sentence-transformers is not installed,
embedding is disabled and only FTS5 keyword search is used.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)

_EMBED_DIM = 512  # bge-small dims; override with FLOAT[384] for MiniLM


class EmbeddingManager:
    """Lazy-loading embedding manager with background indexing queue."""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", enabled: bool = True):
        self._model_name = model_name
        self._enabled = enabled
        self._model = None
        self._model_lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue(maxsize=500)
        self._on_embed: Optional[Callable[[str, list[float]], None]] = None
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
            self._queue.put_nowait((memory_id, text))
        except queue.Full:
            logger.debug("Embedding queue full; skipping %s", memory_id)

    @property
    def available(self) -> bool:
        return self._get_model() is not None

    @property
    def dim(self) -> int:
        """Return embedding dimensions for schema creation."""
        model = self._get_model()
        if model is None:
            return 384  # default fallback
        try:
            vec = model.encode("test")
            return len(vec)
        except Exception:
            return 384

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

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
                memory_id, text = self._queue.get(timeout=1.0)
                vec = self.encode(text)
                if vec is not None and self._on_embed:
                    try:
                        self._on_emit(memory_id, vec)
                    except Exception as exc:
                        logger.debug("Embed callback error: %s", exc)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                logger.debug("Embed worker error: %s", exc)

    def _on_emit(self, memory_id: str, vec: list[float]) -> None:
        if self._on_embed:
            self._on_embed(memory_id, vec)
