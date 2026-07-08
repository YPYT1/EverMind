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

    # LLM extraction (optional, needs api key)
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"

    def db_path(self, space: str) -> Path:
        """Return the SQLite file path for a given project space."""
        slug = space.replace(":", "_").replace("/", "_")
        return self.home / f"{slug}.db"

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key)


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
        llm_api_key=_env("EVERMIND_LLM_API_KEY"),
        llm_model=_env("EVERMIND_LLM_MODEL", "gpt-4o-mini"),
        llm_base_url=_env("EVERMIND_LLM_BASE_URL", "https://api.openai.com/v1"),
    )
