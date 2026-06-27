"""EverMind Archive bridge for Chinese project knowledge files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import config
from .cloud_client import EverMindMCPError


SUMMARY_FILES = (
    "项目概览.md",
    "目录结构.md",
    "模块实现.md",
    "已知坑点.md",
    "修改记录.md",
)

ALLOWED_TARGET_FILES = {
    "项目概览.md",
    "目录结构.md",
    "模块实现.md",
    "运行与配置.md",
    "数据与存储.md",
    "接口与通信.md",
    "测试与验证.md",
    "已知坑点.md",
    "修改记录.md",
    "待办事项.md",
}


@dataclass(frozen=True)
class BasicMemoryCandidate:
    candidate_id: str
    project_slug: str
    target_file: str
    content: str
    evidence: str
    reason: str
    created_at: str


class ArchiveBridge:
    def __init__(
        self,
        *,
        root: str | None = None,
        candidate_dir: str | None = None,
        write_policy: str | None = None,
    ):
        self.root = Path(root or config.EVERMIND_ARCHIVE_ROOT)
        self.candidate_dir = Path(candidate_dir or config.EVERMIND_ARCHIVE_CANDIDATE_DIR)
        self.write_policy = (write_policy or config.EVERMIND_ARCHIVE_WRITE_POLICY).lower()

    @staticmethod
    def project_slug_from_space(space_id: str) -> str | None:
        if not isinstance(space_id, str) or not space_id.startswith("coding:"):
            return None
        slug = space_id.split(":", 1)[1].strip().lower()
        return slug or None

    def read_project_summary(self, project_slug: str, *, max_chars: int = 12000) -> dict:
        slug = self._validate_project_slug(project_slug)
        project_dir = self.root / "projects" / slug
        if not project_dir.exists():
            return {
                "available": False,
                "project_slug": slug,
                "message": f"EverMind Archive project folder not found: {project_dir}",
            }

        sections: list[dict] = []
        remaining = max_chars
        for filename in SUMMARY_FILES:
            if remaining <= 0:
                break
            path = project_dir / filename
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if not text:
                continue
            if filename == "修改记录.md" and len(text) > remaining:
                clipped = text[-remaining:].lstrip()
                truncated_from = "start"
            else:
                clipped = text[:remaining]
                truncated_from = "end"
            sections.append(
                {
                    "file": filename,
                    "path": str(path),
                    "content": clipped,
                    "truncated": len(text) > len(clipped),
                    "truncated_from": truncated_from
                    if len(text) > len(clipped)
                    else None,
                }
            )
            remaining -= len(clipped)

        return {
            "available": bool(sections),
            "project_slug": slug,
            "root": str(project_dir),
            "sections": sections,
        }

    def propose_update(
        self,
        *,
        project_slug: str,
        target_file: str,
        content: str,
        evidence: str,
        reason: str,
    ) -> dict:
        slug = self._validate_project_slug(project_slug)
        filename = self._validate_target_file(target_file)
        if not isinstance(content, str) or not content.strip():
            raise EverMindMCPError("content is required", code="INVALID_INPUT")
        if not isinstance(evidence, str) or not evidence.strip():
            raise EverMindMCPError("evidence is required", code="INVALID_INPUT")
        if not isinstance(reason, str) or not reason.strip():
            raise EverMindMCPError("reason is required", code="INVALID_INPUT")

        candidate = BasicMemoryCandidate(
            candidate_id=f"bm_{uuid4().hex[:16]}",
            project_slug=slug,
            target_file=filename,
            content=content.strip(),
            evidence=evidence.strip(),
            reason=reason.strip(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.candidate_dir.mkdir(parents=True, exist_ok=True)
        path = self.candidate_dir / f"{candidate.candidate_id}.json"
        path.write_text(
            json.dumps(candidate.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "ok": True,
            "candidate_id": candidate.candidate_id,
            "project_slug": slug,
            "target_file": filename,
            "candidate_path": str(path),
            "write_policy": self.write_policy,
            "committed": False,
        }

    def commit_update(self, *, candidate_id: str, confirmed: bool = False) -> dict:
        if not confirmed:
            raise EverMindMCPError(
                "confirmed=true is required before writing to EverMind Archive",
                code="INVALID_INPUT",
            )
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            raise EverMindMCPError("candidate_id is required", code="INVALID_INPUT")

        path = self.candidate_dir / f"{candidate_id.strip()}.json"
        if not path.exists():
            raise EverMindMCPError("candidate not found", code="NOT_FOUND")

        payload = json.loads(path.read_text(encoding="utf-8"))
        slug = self._validate_project_slug(str(payload.get("project_slug", "")))
        filename = self._validate_target_file(str(payload.get("target_file", "")))
        content = str(payload.get("content", "")).strip()
        evidence = str(payload.get("evidence", "")).strip()
        reason = str(payload.get("reason", "")).strip()
        if not content or not evidence:
            raise EverMindMCPError("candidate is missing content/evidence", code="INVALID_INPUT")

        note_path = f"projects/{slug}/{filename}"
        note_dir = self.root / "projects" / slug
        note_file = note_dir / filename
        append_content = (
            f"\n\n## 候选提交 {datetime.now(timezone.utc).date().isoformat()}\n\n"
            f"**原因**：{reason or '未说明'}\n\n"
            f"**证据**：{evidence}\n\n"
            f"{content}\n"
        )

        note_dir.mkdir(parents=True, exist_ok=True)
        if note_file.exists():
            with note_file.open("a", encoding="utf-8", newline="") as handle:
                handle.write(append_content)
            action = "append"
        else:
            title = filename.removesuffix(".md")
            frontmatter = (
                "---\n"
                f"title: {title}\n"
                "type: note\n"
                f"permalink: main/projects/{slug}/{title}\n"
                "---\n\n"
            )
            note_file.write_text(
                frontmatter + append_content.lstrip(),
                encoding="utf-8",
                newline="",
            )
            action = "create"
        return {
            "ok": True,
            "candidate_id": candidate_id.strip(),
            "project_slug": slug,
            "target_file": filename,
            "note_path": note_path,
            "action": action,
            "write_method": "direct_markdown",
        }

    @staticmethod
    def _validate_project_slug(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise EverMindMCPError("project_slug is required", code="INVALID_INPUT")
        slug = value.strip().lower()
        if any(char in slug for char in "\\/:*?\"<>|") or slug in {".", ".."}:
            raise EverMindMCPError("project_slug contains invalid path characters", code="INVALID_INPUT")
        return slug

    @staticmethod
    def _validate_target_file(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise EverMindMCPError("target_file is required", code="INVALID_INPUT")
        filename = value.strip()
        if any(char in filename for char in "\\/:*?\"<>|") or filename in {".", ".."}:
            raise EverMindMCPError("target_file contains invalid path characters", code="INVALID_INPUT")
        if filename not in ALLOWED_TARGET_FILES and not (
            filename.startswith("模块-") and filename.endswith(".md")
        ):
            raise EverMindMCPError(
                "target_file must be a known Chinese EverMind Archive file or 模块-*.md",
                code="INVALID_INPUT",
            )
        return filename



