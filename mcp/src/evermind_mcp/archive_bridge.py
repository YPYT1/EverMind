"""EverMind source-fused local archive engine."""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .config_v2 import EverMindConfig
from .tool_errors import tool_error_response


ARCHIVE_BACKEND = "source-fused-basic-memory"
ARCHIVE_LICENSE = "AGPL-3.0-or-later"


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

_LOCAL_ARCHIVE_TOOLS = {
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

_PATH_LOCKS: dict[str, threading.Lock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


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
        if tool not in _LOCAL_ARCHIVE_TOOLS:
            return self._with_metadata(tool_error_response(
                tool=tool,
                engine="evermind-archive",
                code="ARCHIVE_UNKNOWN_TOOL",
                message=f"unknown archive tool: {tool}",
            ))

        return self._with_metadata(_call_local_archive(self.config, tool, args))

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
            _safe_child(self.config.archive_root / "projects" / project_slug, target_path)
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
            return {"ok": False, "error": "candidate not found", "candidate_id": candidate_id}

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
            note_file.write_text(f"---\ntitle: {title}\n---\n# {title}\n{entry}", encoding="utf-8")
        return {
            "ok": True,
            "candidate_id": candidate_id,
            "action": action,
            "path": str(note_file),
            "write_method": "direct_markdown",
        }


def _call_local_archive(config: EverMindConfig, tool: str, args: dict) -> dict:
    started = time.perf_counter()
    try:
        if tool == "write_note":
            return _local_route_response(_fast_write_note(config, tool, args, started), args)
        if tool == "read_note":
            return _local_route_response(_fast_read_note(config, tool, args, started), args)
        if tool == "delete_note":
            return _local_route_response(_fast_delete_note(config, tool, args, started), args)
        if tool == "edit_note":
            return _local_route_response(_fast_edit_note(config, tool, args, started), args)
        if tool == "build_context":
            return _local_route_response(_fast_build_context(config, tool, args, started), args)
        if tool == "recent_activity":
            return _local_route_response(_fast_recent_activity(config, tool, args, started), args)
        if tool == "search_notes":
            return _local_route_response(_fast_search_notes(config, tool, args, started), args)
        if tool == "list_memory_projects":
            return _local_route_response(_fast_list_memory_projects(config, tool, started), args)
        if tool == "list_workspaces":
            return _local_route_response(_fast_list_workspaces(tool, started), args)
        if tool == "schema_validate":
            return _local_route_response(_fast_schema_validate(config, tool, args, started), args)
        if tool == "schema_infer":
            return _local_route_response(_fast_schema_infer(config, tool, args, started), args)
        if tool == "schema_diff":
            return _local_route_response(_fast_schema_diff(config, tool, args, started), args)
    except KeyError as exc:
        return tool_error_response(
            tool=tool,
            engine="evermind-archive",
            code="ARCHIVE_INVALID_ARGUMENT",
            message=f"missing required argument: {exc.args[0]}",
            hint="Check the tool schema and provide all required arguments.",
            latency_ms=_elapsed_ms(started),
        )
    except ValueError as exc:
        return tool_error_response(
            tool=tool,
            engine="evermind-archive",
            code="ARCHIVE_INVALID_ARGUMENT",
            message=str(exc),
            hint="Check note identifiers, project names, and path-like arguments.",
            latency_ms=_elapsed_ms(started),
        )
    except OSError as exc:
        return tool_error_response(
            tool=tool,
            engine="evermind-archive",
            code="ARCHIVE_IO_ERROR",
            message=str(exc),
            hint="Check archive root permissions and disk availability.",
            retryable=True,
            latency_ms=_elapsed_ms(started),
        )

    return tool_error_response(
        tool=tool,
        engine="evermind-archive",
        code="ARCHIVE_UNSUPPORTED_TOOL",
        message=f"local archive does not support tool: {tool}",
        latency_ms=_elapsed_ms(started),
    )


def _local_route_response(response: dict, args: dict) -> dict:
    if response.get("ok"):
        cloud_requested = bool(args.get("cloud"))
        response.setdefault("route", "local")
        response.setdefault("backend", ARCHIVE_BACKEND)
        response.setdefault("license", ARCHIVE_LICENSE)
        response.setdefault("cloud_requested", cloud_requested)
        response.setdefault("cloud_disabled", cloud_requested)
    return response


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
        return tool_error_response(
            tool=tool,
            engine="evermind-archive",
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
        identifier=_identifier_for_any_project(config, path),
        content=text,
    )


def _fast_read_note(config: EverMindConfig, tool: str, args: dict, started: float) -> dict:
    path = _note_path_from_identifier(config, args, str(args["identifier"]))
    if not path.exists():
        return tool_error_response(
            tool=tool,
            engine="evermind-archive",
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

    operation = str(args["operation"])
    content = str(args["content"])
    with _file_lock(path):
        if not path.exists():
            return tool_error_response(
                tool=tool,
                engine="evermind-archive",
                code="ARCHIVE_NOTE_NOT_FOUND",
                message=f"note not found: {args['identifier']}",
                latency_ms=_elapsed_ms(started),
            )
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
        return tool_error_response(
            tool=tool,
            engine="evermind-archive",
            code="ARCHIVE_NOTE_NOT_FOUND",
            message=f"context source not found: {args['url']}",
            latency_ms=_elapsed_ms(started),
        )
    text = _strip_frontmatter(path.read_text(encoding="utf-8"))
    max_related = int(args.get("max_related") or 5)
    primary_summary = _note_summary(config, args, path)
    backlinks = _backlinks(config, args, path, primary_summary)
    related = _search_note_files(
        config,
        args,
        _title_from_text(text, path),
        limit=max_related + len(backlinks),
    )
    related = _dedupe_context_items([*backlinks, *related], primary_summary["identifier"])[:max_related]
    return _archive_success(
        tool,
        started,
        url=args["url"],
        primary={"path": str(path), "content": text, "summary": primary_summary},
        backlinks=backlinks,
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
        "engine": "evermind-archive",
        "backend": ARCHIVE_BACKEND,
        "license": ARCHIVE_LICENSE,
        "latency_ms": _elapsed_ms(started),
        "native": True,
        "fast_path": True,
        **values,
    }


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _project_root(config: EverMindConfig, args: dict) -> Path:
    project = str(args.get("project") or args.get("project_id") or "default")
    root = archive_project_path(config, project)
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


def archive_project_path(config: EverMindConfig, project: str) -> Path:
    """Return the platform-safe archive directory for a catalog project."""
    return config.archive_root / "projects" / _safe_slug(project)


@contextmanager
def _file_lock(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    started = time.perf_counter()
    fd: int | None = None
    in_process_lock = _path_lock(path)
    acquired = in_process_lock.acquire(timeout=timeout_seconds)
    if not acquired:
        raise TimeoutError(f"timed out waiting for in-process archive lock: {path}")
    try:
        while fd is None:
            _remove_stale_lock(lock_path, older_than_seconds=30.0)
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except (FileExistsError, PermissionError):
                if time.perf_counter() - started > timeout_seconds:
                    raise TimeoutError(f"timed out waiting for archive lock: {lock_path}")
                time.sleep(0.01)
        try:
            owner = json.dumps({"pid": os.getpid(), "created_at": time.time()}).encode("utf-8")
            os.write(fd, owner)
            os.fsync(fd)
            yield
        finally:
            os.close(fd)
            _unlink_with_retry(lock_path)
    finally:
        in_process_lock.release()


def _path_lock(path: Path) -> threading.Lock:
    key = str(path.resolve()).casefold() if os.name == "nt" else str(path.resolve())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[key] = lock
        return lock


def _remove_stale_lock(lock_path: Path, older_than_seconds: float) -> None:
    try:
        stat = lock_path.stat()
    except FileNotFoundError:
        return
    try:
        owner = json.loads(lock_path.read_text(encoding="utf-8"))
        pid = int(owner["pid"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pid = 0
    if pid > 0 and not _pid_is_running(pid):
        _unlink_with_retry(lock_path)
        return
    age = time.time() - stat.st_mtime
    if age > older_than_seconds:
        _unlink_with_retry(lock_path)


def _pid_is_running(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


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
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp, path)
    finally:
        if tmp.exists():
            _unlink_with_retry(tmp)


def _replace_with_retry(source: Path, target: Path, attempts: int = 8) -> None:
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.02 * (attempt + 1))


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


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    data: dict[str, object] = {}
    current_list: str | None = None
    for line in text[4:end].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith("  - ") and current_list:
            value = line[4:].strip()
            data.setdefault(current_list, [])
            if isinstance(data[current_list], list):
                data[current_list].append(value)
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        value = raw.strip()
        if value:
            data[key] = value.strip("'\"")
            current_list = None
        else:
            data[key] = []
            current_list = key
    return data


def _frontmatter_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    raw = str(value).strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    return [item.strip().strip("'\"") for item in raw.split(",") if item.strip()]


def _extract_relations(text: str) -> list[dict]:
    relations: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(r"\[\[([^\]]+)\]\]", text):
        target = match.group(1).split("|", 1)[0].strip()
        key = ("wikilink", target.casefold())
        if target and key not in seen:
            seen.add(key)
            relations.append({"type": "wikilink", "target": target})
    for match in re.finditer(r"\[([^\]]+)\]\((memory://[^)]+)\)", text):
        label, target = match.groups()
        target = target.removeprefix("memory://").strip()
        key = ("memory_link", target.casefold())
        if target and key not in seen:
            seen.add(key)
            relations.append({"type": "memory_link", "target": target, "label": label})
    return relations


def _extract_observations(text: str, limit: int = 20) -> list[str]:
    observations: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        item = stripped[2:].strip()
        if not item or item.startswith("["):
            continue
        observations.append(item)
        if len(observations) >= limit:
            break
    return observations


def _note_matches_filters(summary: dict, args: dict) -> bool:
    requested_tags = set(_arg_values(args.get("tags")))
    if requested_tags and not requested_tags <= set(summary.get("tags", [])):
        return False

    requested_type = set(_arg_values(args.get("type")))
    if requested_type and str(summary.get("type", "")) not in requested_type:
        return False

    requested_status = set(_arg_values(args.get("status")))
    if requested_status and str(summary.get("status", "")) not in requested_status:
        return False

    requested_category = set(_arg_values(args.get("category")))
    if requested_category and not requested_category <= set(summary.get("category", [])):
        return False

    after_date = str(args.get("after_date") or "")
    if after_date and len(after_date) >= 10:
        try:
            cutoff = time.mktime(time.strptime(after_date[:10], "%Y-%m-%d")) * 1000
        except ValueError:
            cutoff = 0
        if cutoff and int(summary.get("modified_at") or 0) < cutoff:
            return False
    return True


def _arg_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    raw = str(value).strip()
    if not raw:
        return []
    return [raw]


def _backlinks(config: EverMindConfig, args: dict, path: Path, primary: dict) -> list[dict]:
    identifiers = {
        str(primary.get("identifier", "")).casefold(),
        str(primary.get("title", "")).casefold(),
        path.stem.casefold(),
    }
    backlinks = []
    for candidate in _note_files(config, args):
        if candidate.resolve() == path.resolve():
            continue
        summary = _note_summary(config, args, candidate)
        for relation in summary.get("relations", []):
            target = str(relation.get("target") or "").removeprefix("memory://").casefold()
            if target in identifiers:
                item = dict(summary)
                item["relation"] = "backlink"
                backlinks.append(item)
                break
    return backlinks


def _dedupe_context_items(items: list[dict], primary_identifier: str) -> list[dict]:
    seen = {primary_identifier}
    unique = []
    for item in items:
        identifier = str(item.get("identifier") or "")
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        unique.append(item)
    return unique


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
    frontmatter = _parse_frontmatter(text)
    content = _strip_frontmatter(text)
    stat = path.stat()
    summary = {
        "title": _title_from_text(content, path),
        "type": str(frontmatter.get("type") or "note"),
        "tags": _frontmatter_list(frontmatter.get("tags")),
        "status": str(frontmatter.get("status") or ""),
        "category": _frontmatter_list(frontmatter.get("category")),
        "path": str(path),
        "identifier": _response_identifier_for_path(config, args, path),
        "modified_at": int(stat.st_mtime * 1000),
        "score": score,
        "excerpt": _excerpt(content),
        "relations": _extract_relations(content),
        "observations": _extract_observations(content),
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
        summary = _note_summary(config, args, path)
        if not _note_matches_filters(summary, args):
            continue
        haystack = text.casefold()
        relation_haystack = " ".join(
            str(relation.get("target", "")) for relation in summary["relations"]
        ).casefold()
        tag_haystack = " ".join(summary["tags"]).casefold()
        title_haystack = summary["title"].casefold()
        score = (
            sum(haystack.count(term) for term in terms)
            + sum(3 * title_haystack.count(term) for term in terms)
            + sum(2 * tag_haystack.count(term) for term in terms)
            + sum(2 * relation_haystack.count(term) for term in terms)
            if terms
            else 1
        )
        if terms and score == 0:
            continue
        summary["score"] = score
        matches.append(summary)
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
