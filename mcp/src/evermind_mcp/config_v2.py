"""Simplified zero-config configuration for EverMind v2."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .project_detector import detect_project_space


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass
class EverMindConfig:
    # Storage
    home: Path = field(default_factory=lambda: Path.home() / ".evermind")
    default_space: str = ""

    # Embedding (optional)
    embed_model: str = "BAAI/bge-small-zh-v1.5"
    embed_enabled: bool = True
    embed_dim: int = 512  # auto-detected, not from env

    # Briefing
    briefing_recent: int = 8          # env: EVERMIND_BRIEFING_RECENT
    briefing_important: int = 5       # env: EVERMIND_BRIEFING_IMPORTANT

    # Graph
    graph_enabled: bool = True        # env: EVERMIND_GRAPH_ENABLED

    # Jieba / cosine dedup
    jieba_enabled: bool = True
    cosine_dedup_threshold: float = 0.95

    def db_path(self, space: str) -> Path:
        """Return the SQLite file path for a given project space."""
        slug = space.replace(":", "_").replace("/", "_")
        return self.home / f"{slug}.db"


def load_config(cwd: str | None = None) -> EverMindConfig:
    """Load config from environment, falling back to sensible defaults."""
    home_env = _env("EVERMIND_HOME")
    home = Path(home_env) if home_env else Path.home() / ".evermind"
    home.mkdir(parents=True, exist_ok=True)

    space = _env("EVERMIND_DEFAULT_SPACE") or detect_project_space(cwd)

    return EverMindConfig(
        home=home,
        default_space=space,
        embed_model=_env("EVERMIND_EMBED_MODEL", "BAAI/bge-small-zh-v1.5"),
        embed_enabled=_env("EVERMIND_EMBED_ENABLED", "true").lower() != "false",
        briefing_recent=int(_env("EVERMIND_BRIEFING_RECENT", "8")),
        briefing_important=int(_env("EVERMIND_BRIEFING_IMPORTANT", "5")),
        graph_enabled=_env("EVERMIND_GRAPH_ENABLED", "true").lower() != "false",
        jieba_enabled=_env("EVERMIND_JIEBA_ENABLED", "true").lower() != "false",
        cosine_dedup_threshold=float(_env("EVERMIND_COSINE_DEDUP_THRESHOLD", "0.95")),
    )
