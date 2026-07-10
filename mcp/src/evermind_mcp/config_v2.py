"""Configuration for EverMind v2."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .bundle_manifest import find_official_bundle_root
from .project_detector import detect_project_space


def _load_dotenv_files(cwd: str | None = None) -> None:
    """Load local .env files when python-dotenv is installed.

    The MCP process is often started from ``mcp/`` while the user-facing
    ``.env`` lives at the repository root, so check both the cwd and parent.
    Environment variables already set by the MCP client keep precedence.
    """
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return

    base = Path(cwd) if cwd else Path.cwd()
    candidates = [base / ".env"]
    if base.name == "mcp":
        candidates.append(base.parent / ".env")
    candidates.append(Path(__file__).resolve().parents[3] / ".env")

    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            load_dotenv(resolved, override=False)


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_any(keys: tuple[str, ...], default: str = "") -> str:
    for key in keys:
        value = os.environ.get(key)
        if value is not None and value != "":
            return value
    return default


def _env_bool(key: str, default: bool) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(key: str, default: int) -> int:
    value = os.environ.get(key)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    value = os.environ.get(key)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass
class EverMindConfig:
    # Storage
    home: Path = field(default_factory=lambda: Path.home() / ".evermind")
    default_space: str = ""
    workspace_root: Path | None = None

    # Shared OpenAI-compatible API settings
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    api_timeout_seconds: float = 30.0

    # Embedding
    embed_provider: str = "auto"  # auto / siliconflow / local
    embed_model: str = "Qwen/Qwen3-Embedding-8B"
    embed_enabled: bool = True
    embed_dim: int = 512
    local_embed_model_path: Path = field(
        default_factory=lambda: _default_local_embed_model_path()
    )
    embed_warmup_on_start: bool = True
    embed_queue_max_retries: int = 5

    # Reranker
    rerank_enabled: bool = True
    rerank_model: str = "Qwen/Qwen3-Reranker-8B"
    rerank_candidates: int = 30
    recall_min_score: float = 0.15
    rerank_instruction: str = (
        "Given a query and a project memory, judge whether the memory helps "
        "answer the query for software engineering work."
    )

    # LLM
    llm_enabled: bool = False
    llm_model: str = "deepseek-ai/DeepSeek-V4-Flash"
    llm_briefing_summary: bool = False

    # Briefing
    briefing_recent: int = 8  # env: EVERMIND_BRIEFING_RECENT
    briefing_important: int = 5  # env: EVERMIND_BRIEFING_IMPORTANT

    # Graph
    graph_enabled: bool = True  # env: EVERMIND_GRAPH_ENABLED

    # Internal archive and code graph exposed through this single MCP
    archive_root: Path = field(default_factory=lambda: Path.home() / "BasicMemory")
    archive_candidate_dir: Path = field(
        default_factory=lambda: Path.home() / "BasicMemory" / ".candidates"
    )
    basic_memory_source_dir: Path = field(
        default_factory=lambda: _default_basic_memory_source_dir()
    )
    codebase_source_dir: Path = field(
        default_factory=lambda: _default_codebase_source_dir()
    )
    codebase_binary_path: Path = field(
        default_factory=lambda: _default_codebase_binary_path()
    )
    codebase_cli_timeout_seconds: float = 120.0

    # Jieba / cosine dedup
    jieba_enabled: bool = True
    cosine_dedup_threshold: float = 0.95
    sensitive_memory_block: bool = True
    auto_reindex_on_start: bool = False

    def db_path(self, space: str) -> Path:
        """Return the shared catalog path; ``space`` is retained for compatibility."""
        del space
        return self.home / "catalog.db"

    def legacy_db_path(self, space: str) -> Path:
        """Return the pre-catalog per-space database path used by migration."""
        slug = space.replace(":", "_").replace("/", "_")
        return self.home / f"{slug}.db"


def load_config(cwd: str | None = None) -> EverMindConfig:
    """Load config from environment, falling back to sensible defaults."""
    _load_dotenv_files(cwd)

    home_env = _env("EVERMIND_HOME")
    home = Path(home_env) if home_env else Path.home() / ".evermind"
    home.mkdir(parents=True, exist_ok=True)
    archive_root_env = _env_any(("EVERMIND_ARCHIVE_ROOT", "BASIC_MEMORY_ROOT"))
    archive_root = (
        Path(archive_root_env) if archive_root_env else Path.home() / "BasicMemory"
    )
    archive_candidate_env = _env("EVERMIND_ARCHIVE_CANDIDATE_DIR")
    archive_candidate_dir = (
        Path(archive_candidate_env)
        if archive_candidate_env
        else archive_root / ".candidates"
    )

    workspace_root = _env_any(
        (
            "EVERMIND_WORKSPACE_ROOT",
            "CURSOR_WORKSPACE",
            "MCP_WORKSPACE_ROOT",
            "WORKSPACE_ROOT",
        )
    )
    detect_cwd = workspace_root or cwd
    space = _env("EVERMIND_DEFAULT_SPACE") or detect_project_space(detect_cwd)
    api_key = _env_any(
        (
            "EVERMIND_SILICONFLOW_API_KEY",
            "SILICONFLOW_API_KEY",
            "EVERMIND_EMBED_API_KEY",
            "EVERMIND_LLM_API_KEY",
        )
    )
    base_url = _env_any(
        (
            "EVERMIND_SILICONFLOW_BASE_URL",
            "EVERMIND_API_BASE_URL",
            "EVERMIND_LLM_BASE_URL",
        ),
        "https://api.siliconflow.cn/v1",
    )
    embed_provider = _env("EVERMIND_EMBED_PROVIDER", "auto")
    embed_model = _env("EVERMIND_EMBED_MODEL", "Qwen/Qwen3-Embedding-8B")
    embed_enabled = _env_bool("EVERMIND_EMBED_ENABLED", True)
    local_embed_model_path = Path(
        _env("EVERMIND_LOCAL_EMBED_MODEL_PATH") or _default_local_embed_model_path()
    )
    llm_enabled_default = bool(api_key) and _env_bool("EVERMIND_LLM_ENABLED", True)

    return EverMindConfig(
        home=home,
        default_space=space,
        workspace_root=Path(detect_cwd or Path.cwd()).resolve(),
        siliconflow_api_key=api_key,
        siliconflow_base_url=base_url,
        api_timeout_seconds=_env_float("EVERMIND_API_TIMEOUT_SECONDS", 30.0),
        embed_provider=embed_provider,
        embed_model=embed_model,
        embed_enabled=embed_enabled,
        embed_dim=_env_int("EVERMIND_EMBED_DIM", 512),
        local_embed_model_path=local_embed_model_path,
        embed_warmup_on_start=_env_bool("EVERMIND_EMBED_WARMUP_ON_START", True),
        embed_queue_max_retries=_env_int("EVERMIND_EMBED_QUEUE_MAX_RETRIES", 5),
        rerank_enabled=_env_bool("EVERMIND_RERANK_ENABLED", True),
        rerank_model=_env("EVERMIND_RERANK_MODEL", "Qwen/Qwen3-Reranker-8B"),
        rerank_candidates=_env_int("EVERMIND_RERANK_CANDIDATES", 30),
        recall_min_score=_env_float("EVERMIND_RECALL_MIN_SCORE", 0.15),
        rerank_instruction=_env(
            "EVERMIND_RERANK_INSTRUCTION", EverMindConfig.rerank_instruction
        ),
        llm_enabled=llm_enabled_default,
        llm_model=_env("EVERMIND_LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash"),
        llm_briefing_summary=_env_bool("EVERMIND_LLM_BRIEFING_SUMMARY", False),
        briefing_recent=_env_int("EVERMIND_BRIEFING_RECENT", 8),
        briefing_important=_env_int("EVERMIND_BRIEFING_IMPORTANT", 5),
        graph_enabled=_env_bool("EVERMIND_GRAPH_ENABLED", True),
        archive_root=archive_root,
        archive_candidate_dir=archive_candidate_dir,
        basic_memory_source_dir=_default_basic_memory_source_dir(),
        codebase_source_dir=_default_codebase_source_dir(),
        codebase_binary_path=_default_codebase_binary_path(),
        codebase_cli_timeout_seconds=_env_float(
            "EVERMIND_CODEBASE_CLI_TIMEOUT_SECONDS", 120.0
        ),
        jieba_enabled=_env_bool("EVERMIND_JIEBA_ENABLED", True),
        cosine_dedup_threshold=_env_float("EVERMIND_COSINE_DEDUP_THRESHOLD", 0.95),
        sensitive_memory_block=_env_bool("EVERMIND_SENSITIVE_MEMORY_BLOCK", True),
        auto_reindex_on_start=_env_bool("EVERMIND_AUTO_REINDEX_ON_START", False),
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_codebase_binary_path() -> Path:
    name = "codebase-memory-mcp.exe" if os.name == "nt" else "codebase-memory-mcp"
    bundle_root = find_official_bundle_root()
    if bundle_root is not None:
        return bundle_root / "bin" / name
    return _repo_root() / "third_party" / "codebase-memory-mcp" / "build" / "c" / name


def _default_local_embed_model_path() -> Path:
    bundle_root = find_official_bundle_root()
    if bundle_root is not None:
        return bundle_root / "models" / "multilingual-e5-small"
    return _repo_root() / "third_party" / "models" / "multilingual-e5-small"


def _default_basic_memory_source_dir() -> Path:
    bundle_root = find_official_bundle_root()
    if bundle_root is not None:
        return bundle_root / "sources" / "basic-memory"
    return _repo_root() / "third_party" / "basic-memory"


def _default_codebase_source_dir() -> Path:
    bundle_root = find_official_bundle_root()
    if bundle_root is not None:
        return bundle_root / "sources" / "codebase-memory-mcp"
    return _repo_root() / "third_party" / "codebase-memory-mcp"
