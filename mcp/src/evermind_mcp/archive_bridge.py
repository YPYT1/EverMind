"""EverMind reviewed-candidate archive operations."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config_v2 import EverMindConfig
from .tool_errors import tool_error_response


ARCHIVE_BACKEND = "source-fused-basic-memory"
ARCHIVE_LICENSE = "AGPL-3.0-or-later"
ARCHIVE_TOOL_NAMES = {
    "propose_basic_memory_update",
    "commit_basic_memory_update",
}


@dataclass
class ArchiveBridge:
    config: EverMindConfig

    def metadata(self) -> dict:
        source = self.config.basic_memory_source_dir
        source_integrated = (
            (source / "LICENSE").is_file()
            and (source / "pyproject.toml").is_file()
            and (source / "src" / "basic_memory" / "mcp").is_dir()
            and (source / "src" / "basic_memory" / "markdown").is_dir()
        )
        return {
            "backend": ARCHIVE_BACKEND,
            "source_integrated": source_integrated,
            "source_path": str(source),
            "license": ARCHIVE_LICENSE,
            "mode": "local",
            "cloud_enabled": False,
            "bridge_runtime_allowed": False,
        }

    def call(self, tool: str, arguments: dict | None = None) -> dict:
        args = arguments or {}
        if tool == "propose_basic_memory_update":
            return self._with_metadata(self.propose_update(**args))
        if tool == "commit_basic_memory_update":
            return self._with_metadata(self.commit_update(**args))
        return self._with_metadata(
            tool_error_response(
                tool=tool,
                engine="evermind-archive",
                code="ARCHIVE_UNKNOWN_TOOL",
                message=f"unknown archive tool: {tool}",
            )
        )

    def _with_metadata(self, response: dict) -> dict:
        response.update(self.metadata())
        return response

    def propose_update(
        self,
        project_slug: str,
        target_file: str,
        content: str,
        evidence: str = "",
        reason: str = "",
    ) -> dict:
        try:
            project_slug = _safe_slug(project_slug)
            target_path = _normalize_identifier(target_file)
            _safe_child(
                self.config.archive_root / "projects" / project_slug,
                target_path,
            )
        except ValueError as exc:
            return tool_error_response(
                tool="propose_basic_memory_update",
                engine="evermind-archive",
                code="ARCHIVE_INVALID_ARGUMENT",
                message=str(exc),
                hint="Use a relative target path inside the archive project.",
            )

        candidate_dir = self.config.archive_candidate_dir
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate_id = f"bm_{uuid.uuid4().hex}"
        payload = {
            "candidate_id": candidate_id,
            "project_slug": project_slug,
            "target_file": target_path.as_posix(),
            "content": content,
            "evidence": evidence,
            "reason": reason,
        }
        path = candidate_dir / f"{candidate_id}.json"
        path.write_text(_to_json(payload), encoding="utf-8")
        return {
            "ok": True,
            "candidate_id": candidate_id,
            "candidate_path": str(path),
            "write_policy": "candidate",
            "requires_confirmation": True,
        }

    def commit_update(self, candidate_id: str, confirmed: bool = False) -> dict:
        if not confirmed:
            return {
                "ok": False,
                "error": "confirmed=true is required before writing EverMind archive files",
                "candidate_id": candidate_id,
            }
        if re.fullmatch(r"bm_[0-9a-f]{32}", candidate_id) is None:
            return tool_error_response(
                tool="commit_basic_memory_update",
                engine="evermind-archive",
                code="ARCHIVE_INVALID_ARGUMENT",
                message="candidate_id must be a generated EverMind candidate ID",
                hint="Use the candidate_id returned by propose_basic_memory_update.",
            )

        path = _safe_child(
            self.config.archive_candidate_dir,
            Path(f"{candidate_id}.json"),
        )
        if not path.exists():
            return {
                "ok": False,
                "error": "candidate not found",
                "candidate_id": candidate_id,
            }

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            project_slug = _safe_slug(str(payload["project_slug"]))
            target_file = _normalize_identifier(str(payload["target_file"]))
            note_file = _safe_child(
                self.config.archive_root / "projects" / project_slug,
                target_file,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return tool_error_response(
                tool="commit_basic_memory_update",
                engine="evermind-archive",
                code="ARCHIVE_INVALID_ARGUMENT",
                message=f"invalid archive candidate: {exc}",
                hint="Create a new candidate with propose_basic_memory_update.",
            )

        note_file.parent.mkdir(parents=True, exist_ok=True)
        entry = _format_candidate_entry(payload)
        action = "append" if note_file.exists() else "create"
        if action == "append":
            with note_file.open("a", encoding="utf-8") as handle:
                handle.write(entry)
        else:
            title = Path(target_file).stem
            note_file.write_text(
                f"---\ntitle: {title}\n---\n# {title}\n{entry}",
                encoding="utf-8",
            )
        return {
            "ok": True,
            "candidate_id": candidate_id,
            "action": action,
            "path": str(note_file),
            "write_method": "direct_markdown",
        }


def _normalize_identifier(identifier: str) -> Path:
    if not identifier.strip():
        raise ValueError("identifier must not be empty")
    normalized = identifier.strip().replace("\\", "/")
    if "://" in normalized:
        normalized = normalized.split("://", 1)[1]
    path = Path(normalized)
    if (
        path.is_absolute()
        or re.match(r"^[A-Za-z]:/", normalized)
        or any(part == ".." for part in path.parts)
    ):
        raise ValueError("identifier must be a relative path inside the archive project")
    return Path(normalized.strip("/"))


def _safe_child(root: Path, child: Path) -> Path:
    root_resolved = root.resolve()
    target = (root_resolved / child).resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise ValueError("path escapes archive project root")
    return target


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", value.strip())
    slug = slug.replace("\\", "-").replace("/", "-").strip("-._")
    return slug or "default"


def archive_project_path(config: EverMindConfig, project: str) -> Path:
    """Return the platform-safe archive directory for a catalog project."""
    return config.archive_root / "projects" / _safe_slug(project)


def _format_candidate_entry(payload: dict) -> str:
    parts = ["\n\n## 记忆更新\n"]
    if payload.get("reason"):
        parts.append(f"\n**原因**：{payload['reason']}\n")
    if payload.get("evidence"):
        parts.append(f"\n**证据**：{payload['evidence']}\n")
    parts.append("\n")
    parts.append(payload["content"].strip())
    parts.append("\n")
    return "".join(parts)


def _to_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
