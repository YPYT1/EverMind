"""Auto-detect project space from git remote URL."""
from __future__ import annotations
import re
import subprocess
from pathlib import Path


_SLUG_RE = re.compile(r"[^a-z0-9-]")


def _slugify(name: str) -> str:
    # lower-case, replace underscores and any other non-slug chars with dashes
    slug = _SLUG_RE.sub("-", name.lower().replace("_", "-"))
    return slug.strip("-") or "default"


def detect_project_space(cwd: str | None = None) -> str:
    """Return coding:<slug> derived from git remote origin URL.

    Falls back to coding:default when not in a git repo or no remote set.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=3,
        )
        if result.returncode != 0:
            return _fallback_from_dir(cwd)
        url = result.stdout.strip()
        return "coding:" + _slug_from_url(url)
    except Exception:
        return _fallback_from_dir(cwd)


def _slug_from_url(url: str) -> str:
    """Extract repo slug from git URL.

    Handles:
      git@github.com:user/my-app.git
      https://github.com/user/my-app.git
      https://github.com/user/my-app
    """
    # Strip .git suffix
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    # Get last path component
    name = url.split("/")[-1]
    if ":" in name:
        name = name.split(":")[-1]
    return _slugify(name) or "default"


def _fallback_from_dir(cwd: str | None) -> str:
    """Use directory name as project slug when git info unavailable."""
    try:
        path = Path(cwd) if cwd else Path.cwd()
        return "coding:" + _slugify(path.name)
    except Exception:
        return "coding:default"
