"""Unified logical-project and repository-workspace identity."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from .storage import EmbeddedStorage


class UnifiedProjectResolver:
    def __init__(self, storage: EmbeddedStorage) -> None:
        self.storage = storage

    def resolve_workspace(self, repo_path: str | Path) -> dict:
        root = _git_root(Path(repo_path))
        canonical_path = _canonical_path(root)
        remote = _selected_remote(root)
        remote_fingerprint = _normalize_remote(remote) if remote else None
        workspace_id = _stable_id("ws", canonical_path)
        now = int(time.time() * 1000)

        with self.storage._write_lock:
            conn = self.storage.conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    "SELECT project_id FROM workspaces WHERE canonical_path=?",
                    (canonical_path,),
                ).fetchone()
                project_id = (
                    _stable_id("prj", remote_fingerprint)
                    if remote_fingerprint
                    else (
                        existing["project_id"]
                        if existing
                        else f"prj-{uuid.uuid4().hex}"
                    )
                )
                conn.execute(
                    """
                    INSERT INTO projects
                        (project_id, remote_fingerprint, display_name, state,
                         created_at, updated_at, detached_at)
                    VALUES (?, ?, ?, 'active', ?, ?, NULL)
                    ON CONFLICT(project_id) DO UPDATE SET
                        remote_fingerprint=COALESCE(excluded.remote_fingerprint,
                                                    projects.remote_fingerprint),
                        display_name=excluded.display_name,
                        state='active', updated_at=excluded.updated_at, detached_at=NULL
                    """,
                    (project_id, remote_fingerprint, root.name, now, now),
                )
                conn.execute(
                    """
                    INSERT INTO workspaces
                        (workspace_id, project_id, canonical_path, git_identity,
                         display_name, state, created_at, updated_at, detached_at)
                    VALUES (?, ?, ?, ?, ?, 'active', ?, ?, NULL)
                    ON CONFLICT(canonical_path) DO UPDATE SET
                        workspace_id=excluded.workspace_id,
                        project_id=excluded.project_id,
                        git_identity=excluded.git_identity,
                        display_name=excluded.display_name,
                        state='active', updated_at=excluded.updated_at, detached_at=NULL
                    """,
                    (
                        workspace_id,
                        project_id,
                        canonical_path,
                        remote_fingerprint,
                        root.name,
                        now,
                        now,
                    ),
                )
                operation_id = "create-" + workspace_id.removeprefix("ws-")
                conn.execute(
                    """
                    INSERT INTO project_operations
                        (operation_id, kind, state, payload, completed_steps,
                         error, created_at, updated_at)
                    VALUES (?, 'create_project', 'completed', ?, ?, NULL, ?, ?)
                    ON CONFLICT(operation_id) DO UPDATE SET
                        state='completed', payload=excluded.payload,
                        completed_steps=excluded.completed_steps,
                        error=NULL, updated_at=excluded.updated_at
                    """,
                    (
                        operation_id,
                        json.dumps(
                            {
                                "project_id": project_id,
                                "workspace_id": workspace_id,
                                "canonical_path": canonical_path,
                            }
                        ),
                        json.dumps(["project", "workspace"]),
                        now,
                        now,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return {
            "project_id": project_id,
            "workspace_id": workspace_id,
            "canonical_path": canonical_path,
            "remote_fingerprint": remote_fingerprint,
            "display_name": root.name,
        }

    def resolve_project(self, identifier: str | Path) -> dict:
        value = str(identifier).strip()
        if not value:
            raise ValueError("project identifier is required")
        conn = self.storage.conn
        row = conn.execute(
            "SELECT * FROM projects WHERE project_id=?", (value,)
        ).fetchone()
        if row is not None:
            return dict(row)

        workspace = conn.execute(
            """
            SELECT project.* FROM workspaces workspace
            JOIN projects project ON project.project_id=workspace.project_id
            WHERE workspace.workspace_id=? OR workspace.canonical_path=?
            """,
            (value, _canonical_path(Path(value)) if _looks_like_path(value) else value),
        ).fetchone()
        if workspace is not None:
            return dict(workspace)

        bindings = conn.execute(
            """
            SELECT project.* FROM basic_project_bindings binding
            JOIN projects project ON project.project_id=binding.project_id
            WHERE binding.basic_external_id=? OR binding.basic_name=? OR binding.basic_path=?
            """,
            (value, value, value),
        ).fetchall()
        named = conn.execute(
            "SELECT * FROM projects WHERE display_name=? AND state='active'", (value,)
        ).fetchall()
        candidates = {row["project_id"]: row for row in [*bindings, *named]}
        if not candidates:
            raise ValueError(f"unknown project: {value}")
        if len(candidates) > 1:
            raise ValueError(f"ambiguous project name: {value}")
        return dict(next(iter(candidates.values())))

    def resolve_codebase_workspace(self, identifier: str) -> str:
        direct = self.storage.conn.execute(
            "SELECT workspace_id FROM workspaces WHERE workspace_id=?",
            (identifier,),
        ).fetchone()
        if direct is not None:
            return direct["workspace_id"]
        project = self.resolve_project(identifier)
        rows = self.storage.conn.execute(
            """
            SELECT workspace_id FROM workspaces
            WHERE project_id=? AND state='active'
            ORDER BY workspace_id
            """,
            (project["project_id"],),
        ).fetchall()
        if not rows:
            raise ValueError(f"project has no active code workspace: {identifier}")
        if len(rows) > 1:
            raise ValueError(
                f"project has multiple workspaces; pass workspace_id instead: {identifier}"
            )
        return rows[0]["workspace_id"]

    def bind_basic_project(
        self,
        project_id: str,
        *,
        external_id: str,
        name: str,
        path: str | Path,
    ) -> None:
        now = int(time.time() * 1000)
        operation_id = (
            "bind-basic-" + hashlib.sha256(project_id.encode()).hexdigest()[:24]
        )
        with self.storage._write_lock:
            conn = self.storage.conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                if (
                    conn.execute(
                        "SELECT 1 FROM projects WHERE project_id=?", (project_id,)
                    ).fetchone()
                    is None
                ):
                    raise ValueError(f"unknown project: {project_id}")
                conn.execute(
                    """
                    INSERT INTO basic_project_bindings
                        (project_id, basic_external_id, basic_name, basic_path, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id) DO UPDATE SET
                        basic_external_id=excluded.basic_external_id,
                        basic_name=excluded.basic_name,
                        basic_path=excluded.basic_path,
                        updated_at=excluded.updated_at
                    """,
                    (project_id, external_id, name, str(Path(path).resolve()), now),
                )
                conn.execute(
                    """
                    INSERT INTO project_operations
                        (operation_id, kind, state, payload, completed_steps,
                         error, created_at, updated_at)
                    VALUES (?, 'create_project', 'completed', ?, ?, NULL, ?, ?)
                    ON CONFLICT(operation_id) DO UPDATE SET
                        state='completed', payload=excluded.payload,
                        completed_steps=excluded.completed_steps,
                        error=NULL, updated_at=excluded.updated_at
                    """,
                    (
                        operation_id,
                        json.dumps({"project_id": project_id, "basic_path": str(path)}),
                        json.dumps(["basic_binding"]),
                        now,
                        now,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def _canonical_path(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser().absolute()
    return os.path.normcase(str(resolved)).replace("\\", "/")


def _git_root(path: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return Path(result.stdout.strip()) if result.returncode == 0 else path.resolve()


def _selected_remote(root: Path) -> str | None:
    remotes = subprocess.run(
        ["git", "-C", str(root), "remote"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    names = [name.strip() for name in remotes.stdout.splitlines() if name.strip()]
    selected = (
        "origin" if "origin" in names else (names[0] if len(names) == 1 else None)
    )
    if selected is None:
        return None
    result = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", selected],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return (
        result.stdout.strip()
        if result.returncode == 0 and result.stdout.strip()
        else None
    )


def _normalize_remote(remote: str) -> str:
    value = remote.strip().rstrip("/")
    if "://" in value:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        path = parsed.path
    else:
        match = re.match(r"^(?:[^@]+@)?([^:]+):(.+)$", value)
        if match:
            host, path = match.group(1).lower(), match.group(2)
        else:
            host, path = "local", value
    path = re.sub(r"/+", "/", path).strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]
    return f"{host}/{path}".casefold()


def _looks_like_path(value: str) -> bool:
    return (
        any(separator in value for separator in ("/", "\\"))
        or Path(value).is_absolute()
    )


__all__ = ["UnifiedProjectResolver"]
