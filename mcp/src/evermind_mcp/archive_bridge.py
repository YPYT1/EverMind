"""EverMind bridge for Basic Memory archive tools.

Basic Memory is AGPL-licensed, so EverMind integrates with it through the
installed CLI process instead of importing or vendoring its Python source.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .config_v2 import EverMindConfig
from .tool_bridge import (
    bridge_error_response,
    bridge_failure_response,
    resolve_executable,
    run_json_command,
)


ARCHIVE_TOOL_NAMES = {
    "write_note",
    "read_note",
    "delete_note",
    "edit_note",
    "build_context",
    "recent_activity",
    "search_notes",
    "list_memory_projects",
    "list_workspaces",
    "schema_validate",
    "schema_infer",
    "schema_diff",
    "propose_basic_memory_update",
    "commit_basic_memory_update",
}

_CLI_TOOL_MAP = {
    "write_note": "write-note",
    "read_note": "read-note",
    "delete_note": "delete-note",
    "edit_note": "edit-note",
    "build_context": "build-context",
    "recent_activity": "recent-activity",
    "search_notes": "search-notes",
    "list_memory_projects": "list-projects",
    "list_workspaces": "list-workspaces",
    "schema_validate": "schema-validate",
    "schema_infer": "schema-infer",
    "schema_diff": "schema-diff",
}


@dataclass
class ArchiveBridge:
    config: EverMindConfig

    @property
    def executable(self) -> str | None:
        return resolve_executable(self.config.basic_memory_path, "basic-memory")

    def call(self, tool: str, arguments: dict | None = None) -> dict:
        args = arguments or {}
        if tool == "propose_basic_memory_update":
            return self.propose_update(**args)
        if tool == "commit_basic_memory_update":
            return self.commit_update(**args)
        if tool not in _CLI_TOOL_MAP:
            return bridge_error_response(
                tool=tool,
                engine="basic-memory",
                code="ARCHIVE_UNKNOWN_TOOL",
                message=f"unknown archive tool: {tool}",
            )

        if _should_use_fast_path(self.config, tool, args):
            return _call_fast_path(self.config, tool, args)

        executable = self.executable
        if executable is None:
            return bridge_error_response(
                tool=tool,
                engine="basic-memory",
                code="ARCHIVE_EXECUTABLE_NOT_FOUND",
                message="basic-memory executable not found",
                hint="Run scripts/windows/install-all.ps1 or install basic-memory==0.22.1.",
            )

        command = [executable, "tool", _CLI_TOOL_MAP[tool]]
        command.extend(_archive_args(tool, args))
        result = run_json_command(
            command,
            timeout_seconds=self.config.archive_timeout_seconds,
            allow_text=True,
        )
        response = result.to_dict()
        response["tool"] = tool
        response["engine"] = "basic-memory"
        if result.ok:
            return _unwrap_archive_response(response)
        return bridge_failure_response(
            result,
            tool=tool,
            engine="basic-memory",
            hint="Check Basic Memory installation, project name, and local/cloud routing flags.",
        )

    def propose_update(
        self,
        project_slug: str,
        target_file: str,
        content: str,
        evidence: str = "",
        reason: str = "",
    ) -> dict:
        candidate_dir = self.config.archive_candidate_dir
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate_id = f"bm_{uuid.uuid4().hex}"
        payload = {
            "candidate_id": candidate_id,
            "project_slug": project_slug,
            "target_file": target_file,
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
                "error": "confirmed=true is required before writing Basic Memory files",
                "candidate_id": candidate_id,
            }

        path = self.config.archive_candidate_dir / f"{candidate_id}.json"
        if not path.exists():
            return {"ok": False, "error": "candidate not found", "candidate_id": candidate_id}

        payload = json.loads(path.read_text(encoding="utf-8"))
        project_slug = payload["project_slug"]
        target_file = payload["target_file"]
        note_file = self.config.archive_root / "projects" / project_slug / target_file
        note_file.parent.mkdir(parents=True, exist_ok=True)
        entry = _format_candidate_entry(payload)
        action = "append" if note_file.exists() else "create"
        if action == "append":
            with note_file.open("a", encoding="utf-8") as handle:
                handle.write(entry)
        else:
            title = Path(target_file).stem
            note_file.write_text(f"---\ntitle: {title}\n---\n# {title}\n{entry}", encoding="utf-8")
        return {
            "ok": True,
            "candidate_id": candidate_id,
            "action": action,
            "path": str(note_file),
            "write_method": "direct_markdown",
        }


def _archive_args(tool: str, args: dict) -> list[str]:
    if tool == "write_note":
        command = ["--title", args["title"], "--folder", args["folder"]]
        _append_option(command, "--content", args.get("content"))
        tags = args.get("tags")
        if isinstance(tags, list):
            tags = ",".join(str(tag) for tag in tags)
        _append_option(command, "--tags", tags)
        note_type = args.get("type")
        if isinstance(note_type, list):
            note_type = note_type[0] if note_type else None
        _append_option(command, "--type", note_type)
        _append_project_options(command, args)
        if args.get("overwrite"):
            command.append("--overwrite")
        _append_route(command, args)
        return command

    if tool == "read_note":
        command = [args["identifier"]]
        if args.get("include_frontmatter"):
            command.append("--include-frontmatter")
        _append_project_options(command, args)
        _append_route(command, args)
        return command

    if tool == "delete_note":
        command = [args["identifier"]]
        if args.get("is_directory"):
            command.append("--is-directory")
        _append_project_options(command, args)
        _append_route(command, args)
        return command

    if tool == "edit_note":
        command = [
            args["identifier"],
            "--operation",
            args["operation"],
            "--content",
            args["content"],
        ]
        _append_option(command, "--find-text", args.get("find_text"))
        _append_option(command, "--section", args.get("section"))
        _append_option(command, "--expected-replacements", args.get("expected_replacements"))
        _append_project_options(command, args)
        _append_route(command, args)
        return command

    if tool == "build_context":
        command = [args["url"]]
        for key in ("depth", "timeframe", "page", "page_size", "max_related"):
            _append_option(command, "--" + key.replace("_", "-"), args.get(key))
        _append_project_options(command, args)
        _append_route(command, args)
        return command

    if tool == "recent_activity":
        command = []
        _append_repeat(command, "--type", args.get("type"))
        for key in ("depth", "timeframe", "page", "page_size"):
            _append_option(command, "--" + key.replace("_", "-"), args.get(key))
        _append_project_options(command, args)
        _append_route(command, args)
        return command

    if tool == "search_notes":
        command = []
        _append_positional(command, args.get("query"))
        for flag in ("permalink", "title", "vector", "hybrid"):
            if args.get(flag):
                command.append("--" + flag.replace("_", "-"))
        _append_option(command, "--after_date", args.get("after_date"))
        _append_repeat(command, "--tag", args.get("tags"))
        _append_option(command, "--status", args.get("status"))
        _append_repeat(command, "--type", args.get("type"))
        _append_repeat(command, "--entity-type", args.get("entity_type"))
        _append_repeat(command, "--category", args.get("category"))
        _append_repeat(command, "--meta", args.get("meta"))
        _append_option(command, "--filter", args.get("filter"))
        for key in ("page", "page_size"):
            _append_option(command, "--" + key.replace("_", "-"), args.get(key))
        _append_project_options(command, args)
        _append_route(command, args)
        return command

    if tool in {"list_memory_projects", "list_workspaces"}:
        command = []
        _append_route(command, args)
        return command

    if tool == "schema_validate":
        command = []
        _append_positional(command, args.get("target"))
        _append_project_options(command, args)
        _append_route(command, args)
        return command

    if tool in {"schema_infer", "schema_diff"}:
        command = [args["note_type"]]
        if tool == "schema_infer":
            _append_option(command, "--threshold", args.get("threshold"))
        _append_project_options(command, args)
        _append_route(command, args)
        return command

    return []


_FAST_PATH_TOOLS = {
    "write_note",
    "read_note",
    "delete_note",
    "edit_note",
    "build_context",
    "recent_activity",
    "search_notes",
    "list_memory_projects",
    "list_workspaces",
    "schema_validate",
    "schema_infer",
    "schema_diff",
}


def _should_use_fast_path(config: EverMindConfig, tool: str, args: dict) -> bool:
    return (
        config.archive_fast_path_enabled
        and tool in _FAST_PATH_TOOLS
        and not args.get("cloud")
    )


def _call_fast_path(config: EverMindConfig, tool: str, args: dict) -> dict:
    started = time.perf_counter()
    try:
        if tool == "write_note":
            return _fast_write_note(config, tool, args, started)
        if tool == "read_note":
            return _fast_read_note(config, tool, args, started)
        if tool == "delete_note":
            return _fast_delete_note(config, tool, args, started)
        if tool == "edit_note":
            return _fast_edit_note(config, tool, args, started)
        if tool == "build_context":
            return _fast_build_context(config, tool, args, started)
        if tool == "recent_activity":
            return _fast_recent_activity(config, tool, args, started)
        if tool == "search_notes":
            return _fast_search_notes(config, tool, args, started)
        if tool == "list_memory_projects":
            return _fast_list_memory_projects(config, tool, started)
        if tool == "list_workspaces":
            return _fast_list_workspaces(tool, started)
        if tool == "schema_validate":
            return _fast_schema_validate(config, tool, args, started)
        if tool == "schema_infer":
            return _fast_schema_infer(config, tool, args, started)
        if tool == "schema_diff":
            return _fast_schema_diff(config, tool, args, started)
    except KeyError as exc:
        return bridge_error_response(
            tool=tool,
            engine="basic-memory",
            code="ARCHIVE_INVALID_ARGUMENT",
            message=f"missing required argument: {exc.args[0]}",
            hint="Check the tool schema and provide all required arguments.",
            latency_ms=_elapsed_ms(started),
        )
    except ValueError as exc:
        return bridge_error_response(
            tool=tool,
            engine="basic-memory",
            code="ARCHIVE_INVALID_ARGUMENT",
            message=str(exc),
            hint="Check note identifiers, project names, and path-like arguments.",
            latency_ms=_elapsed_ms(started),
        )
    except OSError as exc:
        return bridge_error_response(
            tool=tool,
            engine="basic-memory",
            code="ARCHIVE_IO_ERROR",
            message=str(exc),
            hint="Check archive root permissions and disk availability.",
            retryable=True,
            latency_ms=_elapsed_ms(started),
        )

    return bridge_error_response(
        tool=tool,
        engine="basic-memory",
        code="ARCHIVE_FAST_PATH_UNSUPPORTED",
        message=f"archive fast path does not support tool: {tool}",
        latency_ms=_elapsed_ms(started),
    )


def _fast_write_note(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    title = str(args["title"]).strip()
    folder = str(args["folder"]).strip()
    if not title:
        raise ValueError("title must not be empty")
    if not folder:
        raise ValueError("folder must not be empty")

    path = _note_path_from_title(config, args, title, folder)
    existed = path.exists()
    if existed and not args.get("overwrite"):
        return bridge_error_response(
            tool=tool,
            engine="basic-memory",
            code="ARCHIVE_NOTE_EXISTS",
            message=f"note already exists: {path}",
            hint="Set overwrite=true to replace the existing note.",
            latency_ms=_elapsed_ms(started),
        )

    content = str(args.get("content") or "")
    text = _render_note(title, content, args)
    with _file_lock(path):
        _atomic_write_text(path, text)
    return _archive_success(
        tool,
        started,
        action="updated" if existed else "created",
        path=str(path),
        identifier=_identifier_for_path(config, args, path),
        content=text,
    )


def _fast_read_note(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    path = _note_path_from_identifier(config, args, str(args["identifier"]))
    if not path.exists():
        return bridge_error_response(
            tool=tool,
            engine="basic-memory",
            code="ARCHIVE_NOTE_NOT_FOUND",
            message=f"note not found: {args['identifier']}",
            latency_ms=_elapsed_ms(started),
        )
    text = path.read_text(encoding="utf-8")
    content = text if args.get("include_frontmatter") else _strip_frontmatter(text)
    return _archive_success(
        tool,
        started,
        path=str(path),
        identifier=_response_identifier_for_path(config, args, path),
        content=content,
    )


def _fast_delete_note(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    target = _note_path_from_identifier(
        config,
        args,
        str(args["identifier"]),
        append_markdown_suffix=not args.get("is_directory"),
    )

    deleted = False
    with _file_lock(target):
        if target.is_dir() and args.get("is_directory"):
            shutil.rmtree(target)
            deleted = True
        elif target.exists() and target.is_file():
            target.unlink()
            deleted = True
    return _archive_success(tool, started, deleted=deleted, path=str(target))


def _fast_edit_note(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    path = _note_path_from_identifier(config, args, str(args["identifier"]))
    if not path.exists():
        return bridge_error_response(
            tool=tool,
            engine="basic-memory",
            code="ARCHIVE_NOTE_NOT_FOUND",
            message=f"note not found: {args['identifier']}",
            latency_ms=_elapsed_ms(started),
        )

    operation = str(args["operation"])
    content = str(args["content"])
    with _file_lock(path):
        old = path.read_text(encoding="utf-8")
        new, replacements = _edit_text(old, operation, content, args)
        _atomic_write_text(path, new)
    return _archive_success(
        tool,
        started,
        action=operation,
        replacements=replacements,
        path=str(path),
        content=new,
    )


def _fast_build_context(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    identifier = str(args["url"]).removeprefix("memory://")
    path = _note_path_from_identifier(config, args, identifier)
    if not path.exists():
        return bridge_error_response(
            tool=tool,
            engine="basic-memory",
            code="ARCHIVE_NOTE_NOT_FOUND",
            message=f"context source not found: {args['url']}",
            latency_ms=_elapsed_ms(started),
        )
    text = _strip_frontmatter(path.read_text(encoding="utf-8"))
    related = _search_note_files(config, args, _title_from_text(text, path), limit=int(args.get("max_related") or 5))
    return _archive_success(
        tool,
        started,
        url=args["url"],
        primary={"path": str(path), "content": text},
        related=related,
    )


def _fast_recent_activity(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    page = max(1, int(args.get("page") or 1))
    page_size = max(1, min(100, int(args.get("page_size") or 10)))
    notes = sorted(_note_files(config, args), key=lambda p: p.stat().st_mtime, reverse=True)
    offset = (page - 1) * page_size
    items = [_note_summary(config, args, path) for path in notes[offset : offset + page_size]]
    return _archive_success(tool, started, activity=items, results=items, count=len(items), total=len(notes))


def _fast_search_notes(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    query = str(args.get("query") or "")
    page = max(1, int(args.get("page") or 1))
    page_size = max(1, min(100, int(args.get("page_size") or 10)))
    matches = _search_note_files(config, args, query, limit=page * page_size)
    offset = (page - 1) * page_size
    results = matches[offset : offset + page_size]
    return _archive_success(tool, started, results=results, notes=results, count=len(results), total=len(matches))


def _fast_list_memory_projects(config: EverMindConfig, tool: str, started: float) -> dict:
    projects_root = config.archive_root / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)
    projects = []
    for path in sorted(projects_root.iterdir()):
        if not path.is_dir():
            continue
        projects.append(
            {
                "name": path.name,
                "path": str(path),
                "note_count": len(list(path.rglob("*.md"))),
            }
        )
    return _archive_success(tool, started, projects=projects, count=len(projects))


def _fast_list_workspaces(tool: str, started: float) -> dict:
    return _archive_success(
        tool,
        started,
        workspaces=[],
        count=0,
        cloud_available=False,
        reason="local_mode_no_cloud",
    )


def _fast_schema_validate(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    notes = list(_note_files(config, args))
    invalid = []
    for path in notes:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            invalid.append({"path": str(path), "error": "empty note"})
    return _archive_success(
        tool,
        started,
        valid=len(invalid) == 0,
        checked=len(notes),
        errors=invalid,
    )


def _fast_schema_infer(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    keys: dict[str, int] = {}
    notes = list(_note_files(config, args))
    for path in notes:
        for key in _frontmatter_keys(path.read_text(encoding="utf-8")):
            keys[key] = keys.get(key, 0) + 1
    return _archive_success(
        tool,
        started,
        note_type=args["note_type"],
        checked=len(notes),
        schema={"fields": keys},
    )


def _fast_schema_diff(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    notes = list(_note_files(config, args))
    return _archive_success(
        tool,
        started,
        note_type=args["note_type"],
        checked=len(notes),
        drift=[],
        status="no_schema" if not notes else "ok",
    )


def _archive_success(tool: str, started: float, **values: object) -> dict:
    return {
        "ok": True,
        "tool": tool,
        "engine": "basic-memory",
        "latency_ms": _elapsed_ms(started),
        "fast_path": True,
        **values,
    }


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _project_root(config: EverMindConfig, args: dict) -> Path:
    project = str(args.get("project") or args.get("project_id") or "default")
    root = config.archive_root / "projects" / _safe_slug(project)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _project_roots(config: EverMindConfig, args: dict) -> list[Path]:
    if args.get("project") or args.get("project_id"):
        return [_project_root(config, args)]
    projects_root = config.archive_root / "projects"
    if not projects_root.exists():
        return []
    return [path for path in projects_root.iterdir() if path.is_dir()]


def _note_path_from_title(config: EverMindConfig, args: dict, title: str, folder: str) -> Path:
    root = _project_root(config, args)
    folder_part = _normalize_identifier(folder)
    filename = _slugify(title) + ".md"
    return _safe_child(root, folder_part / filename)


def _note_path_from_identifier(
    config: EverMindConfig,
    args: dict,
    identifier: str,
    *,
    append_markdown_suffix: bool = True,
) -> Path:
    normalized = _normalize_identifier(identifier.removeprefix("memory://"))
    root, normalized = _root_and_identifier_path(config, args, normalized)
    if append_markdown_suffix and normalized.suffix.lower() != ".md":
        normalized = normalized.with_suffix(".md")
    return _safe_child(root, normalized)


def _root_and_identifier_path(
    config: EverMindConfig,
    args: dict,
    normalized: Path,
) -> tuple[Path, Path]:
    project = args.get("project") or args.get("project_id")
    if project:
        root = _project_root(config, args)
        project_slug = _safe_slug(str(project))
        if len(normalized.parts) > 1 and normalized.parts[0] == project_slug:
            return root, Path(*normalized.parts[1:])
        return root, normalized

    projects_root = config.archive_root / "projects"
    if len(normalized.parts) > 1:
        candidate_root = projects_root / normalized.parts[0]
        if candidate_root.is_dir():
            return candidate_root, Path(*normalized.parts[1:])
    return _project_root(config, args), normalized


def _normalize_identifier(identifier: str) -> Path:
    if not identifier.strip():
        raise ValueError("identifier must not be empty")
    normalized = identifier.strip().replace("\\", "/").strip("/")
    if "://" in normalized:
        normalized = normalized.split("://", 1)[1]
    path = Path(normalized)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError("identifier must be a relative path inside the archive project")
    return path


def _safe_child(root: Path, child: Path) -> Path:
    root_resolved = root.resolve()
    target = (root_resolved / child).resolve()
    if root_resolved != target and root_resolved not in target.parents:
        raise ValueError("path escapes archive project root")
    return target


def _identifier_for_path(config: EverMindConfig, args: dict, path: Path) -> str:
    root = _project_root(config, args).resolve()
    rel = path.resolve().relative_to(root).as_posix()
    return rel[:-3] if rel.endswith(".md") else rel


def _render_note(title: str, content: str, args: dict) -> str:
    frontmatter = {
        "title": title,
        "type": _first_value(args.get("type")) or "note",
        "tags": args.get("tags") or [],
    }
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    lines.extend(["---", f"# {title}", ""])
    if content:
        lines.append(content.rstrip())
        lines.append("")
    return "\n".join(lines)


def _first_value(value: object) -> str | None:
    if isinstance(value, list):
        return str(value[0]) if value else None
    if value is None:
        return None
    return str(value)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", value.strip().lower())
    slug = slug.strip("-._")
    return slug or "note"


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "-", value.strip())
    slug = slug.replace("\\", "-").replace("/", "-").strip("-._")
    return slug or "default"


@contextmanager
def _file_lock(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    started = time.perf_counter()
    fd: int | None = None
    while fd is None:
        _remove_stale_lock(lock_path, older_than_seconds=30.0)
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            if time.perf_counter() - started > timeout_seconds:
                raise TimeoutError(f"timed out waiting for archive lock: {lock_path}")
            time.sleep(0.01)
    try:
        yield
    finally:
        os.close(fd)
        _unlink_with_retry(lock_path)


def _remove_stale_lock(lock_path: Path, older_than_seconds: float) -> None:
    try:
        age = time.time() - lock_path.stat().st_mtime
    except FileNotFoundError:
        return
    if age > older_than_seconds:
        _unlink_with_retry(lock_path)


def _unlink_with_retry(path: Path, attempts: int = 5) -> None:
    for attempt in range(attempts):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.02 * (attempt + 1))


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[end + 5 :].lstrip()
    return text


def _frontmatter_keys(text: str) -> list[str]:
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---\n", 4)
    if end == -1:
        return []
    keys = []
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith(" "):
            keys.append(line.split(":", 1)[0].strip())
    return keys


def _title_from_text(text: str, path: Path) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _note_files(config: EverMindConfig, args: dict) -> Iterator[Path]:
    for root in _project_roots(config, args):
        if root.exists():
            yield from root.rglob("*.md")


def _note_summary(config: EverMindConfig, args: dict, path: Path, score: int = 0) -> dict:
    text = path.read_text(encoding="utf-8")
    content = _strip_frontmatter(text)
    stat = path.stat()
    summary = {
        "title": _title_from_text(content, path),
        "path": str(path),
        "identifier": _identifier_for_any_project(config, path),
        "modified_at": int(stat.st_mtime * 1000),
        "score": score,
        "excerpt": _excerpt(content),
    }
    if args.get("include_content"):
        summary["content"] = content
    return summary


def _identifier_for_any_project(config: EverMindConfig, path: Path) -> str:
    projects_root = (config.archive_root / "projects").resolve()
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(projects_root).as_posix()
    except ValueError:
        rel = resolved.name
    return rel[:-3] if rel.endswith(".md") else rel


def _response_identifier_for_path(config: EverMindConfig, args: dict, path: Path) -> str:
    if args.get("project") or args.get("project_id"):
        return _identifier_for_path(config, args, path)
    return _identifier_for_any_project(config, path)


def _excerpt(text: str, limit: int = 240) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


def _search_note_files(config: EverMindConfig, args: dict, query: str, limit: int) -> list[dict]:
    terms = [term for term in re.split(r"\s+", query.casefold()) if term]
    matches = []
    for path in _note_files(config, args):
        text = path.read_text(encoding="utf-8", errors="ignore")
        haystack = text.casefold()
        score = sum(haystack.count(term) for term in terms) if terms else 1
        if terms and score == 0:
            continue
        matches.append(_note_summary(config, args, path, score=score))
    matches.sort(key=lambda item: (item["score"], item["modified_at"]), reverse=True)
    return matches[:limit]


def _edit_text(old: str, operation: str, content: str, args: dict) -> tuple[str, int]:
    if operation == "append":
        return old.rstrip() + "\n" + content + "\n", 1
    if operation == "prepend":
        return content + "\n" + old.lstrip(), 1
    if operation == "find_replace":
        find_text = str(args.get("find_text") or "")
        if not find_text:
            raise ValueError("find_text is required for find_replace")
        expected = args.get("expected_replacements")
        replacements = old.count(find_text)
        if expected is not None and replacements != int(expected):
            raise ValueError(f"expected {expected} replacements, found {replacements}")
        return old.replace(find_text, content), replacements
    if operation == "replace_section":
        section = str(args.get("section") or "")
        if not section:
            raise ValueError("section is required for replace_section")
        return _replace_markdown_section(old, section, content), 1
    raise ValueError(f"unsupported edit operation: {operation}")


def _replace_markdown_section(old: str, section: str, content: str) -> tuple[str, int]:
    lines = old.splitlines()
    heading_index = None
    heading_level = 0
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            continue
        hashes, _, title = stripped.partition(" ")
        if title.strip() == section:
            heading_index = index
            heading_level = len(hashes)
            break
    if heading_index is None:
        raise ValueError(f"section not found: {section}")
    end = len(lines)
    for index in range(heading_index + 1, len(lines)):
        stripped = lines[index].lstrip()
        if stripped.startswith("#"):
            hashes, _, _ = stripped.partition(" ")
            if len(hashes) <= heading_level:
                end = index
                break
    new_lines = lines[: heading_index + 1] + content.splitlines() + lines[end:]
    return "\n".join(new_lines).rstrip() + "\n", 1


def _append_project_options(command: list[str], args: dict) -> None:
    _append_option(command, "--project", args.get("project"))
    _append_option(command, "--project-id", args.get("project_id"))


def _append_route(command: list[str], args: dict) -> None:
    if args.get("local"):
        command.append("--local")
    if args.get("cloud"):
        command.append("--cloud")


def _append_option(command: list[str], flag: str, value: object | None) -> None:
    if value is None:
        return
    command.extend([flag, str(value)])


def _append_repeat(command: list[str], flag: str, values: object | None) -> None:
    if values is None:
        return
    if isinstance(values, str):
        values = [values]
    for value in values:
        command.extend([flag, str(value)])


def _append_positional(command: list[str], value: object | None) -> None:
    if value is not None:
        command.append(str(value))


def _unwrap_archive_response(response: dict) -> dict:
    data = response.get("data")
    if isinstance(data, dict):
        merged = dict(data)
        merged.setdefault("ok", True)
        merged.setdefault("engine", response["engine"])
        merged.setdefault("tool", response["tool"])
        merged.setdefault("latency_ms", response["latency_ms"])
        return merged
    if data is not None:
        response["ok"] = True
        return response
    response["data"] = response["stdout"]
    response["ok"] = True
    return response


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
