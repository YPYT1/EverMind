"""Idempotent migration from per-space SQLite files into the global catalog."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .storage import EmbeddedStorage, _normalized_content_hash


class LegacyCatalogMigrator:
    def __init__(self, home: Path, storage: EmbeddedStorage) -> None:
        self.home = home
        self.storage = storage
        self.catalog_path = Path(storage._db_path).resolve()

    def migrate(self) -> None:
        sources = [
            path
            for path in sorted(self.home.glob("*.db"))
            if path.resolve() != self.catalog_path
        ]
        if not sources:
            return
        with _migration_lock(self.home / "catalog.migration.lock"):
            for source in sources:
                self._migrate_source(source)
            self._verify_catalog()
            self.storage.set_meta(
                "legacy_migration_complete_v1", str(int(time.time() * 1000))
            )

    def _migrate_source(self, source_path: Path) -> None:
        source_key = str(source_path.resolve())
        operation_id = (
            "migration-" + hashlib.sha256(source_key.encode()).hexdigest()[:24]
        )
        now = int(time.time() * 1000)
        self.storage.conn.execute(
            """
            INSERT INTO project_operations
                (operation_id, kind, state, payload, completed_steps, created_at, updated_at)
            VALUES (?, 'legacy_migration', 'running', ?, '[]', ?, ?)
            ON CONFLICT(operation_id) DO UPDATE SET state='running', updated_at=excluded.updated_at
            """,
            (operation_id, json.dumps({"source_db": source_key}), now, now),
        )
        self.storage.conn.commit()

        backup = self.home / "backups" / f"{source_path.name}.bak"
        self._backup_once(source_path, backup)
        source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        try:
            tables = {
                row["name"]
                for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            legacy_map = self._import_memories(source, source_key, tables)
            self._import_graph(source, source_key, tables, legacy_map)
            self._import_events(source, source_key, tables, legacy_map)
        finally:
            source.close()

        completed = ["backup", "memories", "graph", "events"]
        self.storage.conn.execute(
            """
            UPDATE project_operations
            SET state='completed', completed_steps=?, error=NULL, updated_at=?
            WHERE operation_id=?
            """,
            (json.dumps(completed), int(time.time() * 1000), operation_id),
        )
        self.storage.conn.commit()

    @staticmethod
    def _backup_once(source_path: Path, backup_path: Path) -> None:
        if backup_path.exists():
            return
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = backup_path.with_suffix(backup_path.suffix + ".tmp")
        if temporary.exists():
            temporary.unlink()
        source = sqlite3.connect(source_path)
        destination = sqlite3.connect(temporary)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        os.replace(temporary, backup_path)

    def _import_memories(
        self,
        source: sqlite3.Connection,
        source_key: str,
        tables: set[str],
    ) -> dict[str, str]:
        if "memories" not in tables:
            return {}
        mapped = {
            row["legacy_id"]: row["memory_id"]
            for row in self.storage.conn.execute(
                "SELECT legacy_id, memory_id FROM legacy_memory_map WHERE source_db=?",
                (source_key,),
            ).fetchall()
        }
        columns = {
            row["name"]
            for row in source.execute("PRAGMA table_info(memories)").fetchall()
        }
        for row in source.execute(
            "SELECT rowid, * FROM memories ORDER BY created_at, rowid"
        ):
            legacy_id = str(row["id"])
            if legacy_id in mapped:
                continue
            candidate_id = legacy_id
            collision = self.storage.conn.execute(
                "SELECT content FROM memories WHERE id=?", (candidate_id,)
            ).fetchone()
            if collision and _normalized_content_hash(
                collision["content"]
            ) != _normalized_content_hash(row["content"]):
                candidate_id = None

            tags = _json_value(row, columns, "tags", [])
            meta = _json_value(row, columns, "meta", {})
            memory, _ = self.storage.insert_memory_atomic(
                memory_id=candidate_id,
                space=row["space"],
                content=row["content"],
                layer=_column(row, columns, "layer", "episodic"),
                memory_type=_column(row, columns, "memory_type", "auto"),
                role=_column(row, columns, "role", "user"),
                importance=int(_column(row, columns, "importance", 0)),
                tags=tags if isinstance(tags, list) else [],
                meta=meta if isinstance(meta, dict) else {},
                created_at=int(
                    _column(row, columns, "created_at", int(time.time() * 1000))
                ),
                updated_at=int(
                    _column(row, columns, "updated_at", int(time.time() * 1000))
                ),
                expires_at=_column(row, columns, "expires_at", None),
            )
            self.storage.conn.execute(
                """
                INSERT OR IGNORE INTO legacy_memory_map
                    (source_db, legacy_id, memory_id, imported_at)
                VALUES (?, ?, ?, ?)
                """,
                (source_key, legacy_id, memory.id, int(time.time() * 1000)),
            )
            self.storage.conn.commit()
            mapped[legacy_id] = memory.id
        return mapped

    def _import_graph(
        self,
        source: sqlite3.Connection,
        source_key: str,
        tables: set[str],
        memory_map: dict[str, str],
    ) -> None:
        if "graph_nodes" not in tables or "graph_edges" not in tables:
            return
        node_map: dict[str, str] = {}
        for row in source.execute("SELECT * FROM graph_nodes ORDER BY created_at, id"):
            existing = self.storage.conn.execute(
                """
                SELECT id FROM graph_nodes
                WHERE space=? AND node_type=? AND label=?
                """,
                (row["space"], row["node_type"], row["label"]),
            ).fetchone()
            node_id = (
                existing["id"]
                if existing
                else _collision_safe_id(
                    self.storage.conn, "graph_nodes", row["id"], source_key
                )
            )
            if existing is None:
                self.storage.conn.execute(
                    """
                    INSERT OR IGNORE INTO graph_nodes
                        (id, space, node_type, label, meta, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_id,
                        row["space"],
                        row["node_type"],
                        row["label"],
                        row["meta"],
                        row["created_at"],
                    ),
                )
            node_map[row["id"]] = node_id

        for row in source.execute("SELECT * FROM graph_edges ORDER BY created_at, id"):
            edge_id = _collision_safe_id(
                self.storage.conn, "graph_edges", row["id"], source_key
            )
            meta = _json_text(row["meta"])
            old_memory_id = meta.get("memory_id")
            if old_memory_id in memory_map:
                meta["memory_id"] = memory_map[old_memory_id]
            self.storage.conn.execute(
                """
                INSERT OR IGNORE INTO graph_edges
                    (id, space, src_id, dst_id, edge_type, weight, meta, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge_id,
                    row["space"],
                    node_map[row["src_id"]],
                    node_map[row["dst_id"]],
                    row["edge_type"],
                    row["weight"],
                    json.dumps(meta),
                    row["created_at"],
                ),
            )
        self.storage.conn.commit()

    def _import_events(
        self,
        source: sqlite3.Connection,
        source_key: str,
        tables: set[str],
        memory_map: dict[str, str],
    ) -> None:
        if "event_log" not in tables:
            return
        for row in source.execute("SELECT * FROM event_log ORDER BY created_at, id"):
            event_id = _collision_safe_id(
                self.storage.conn, "event_log", row["id"], source_key
            )
            memory_id = row["memory_id"]
            if memory_id is not None:
                memory_id = memory_map.get(memory_id, memory_id)
                if (
                    self.storage.conn.execute(
                        "SELECT 1 FROM memories WHERE id=?", (memory_id,)
                    ).fetchone()
                    is None
                ):
                    memory_id = None
            self.storage.conn.execute(
                """
                INSERT OR IGNORE INTO event_log
                    (id, space, event_type, memory_id, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    row["space"],
                    row["event_type"],
                    memory_id,
                    row["detail"],
                    row["created_at"],
                ),
            )
        self.storage.conn.commit()

    def _verify_catalog(self) -> None:
        foreign_keys = self.storage.conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise RuntimeError(f"catalog foreign-key check failed: {foreign_keys[:3]}")
        memories = self.storage.conn.execute(
            "SELECT COUNT(*) FROM memories"
        ).fetchone()[0]
        fts_rows = self.storage.conn.execute(
            "SELECT COUNT(*) FROM memories_fts"
        ).fetchone()[0]
        if memories != fts_rows:
            raise RuntimeError(
                f"catalog FTS parity failed: memories={memories}, memories_fts={fts_rows}"
            )


def _column(row: sqlite3.Row, columns: set[str], name: str, default):
    return row[name] if name in columns and row[name] is not None else default


def _json_value(row: sqlite3.Row, columns: set[str], name: str, default):
    value = _column(row, columns, name, None)
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _json_text(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _collision_safe_id(
    conn: sqlite3.Connection, table: str, original_id: str, source_key: str
) -> str:
    del conn, table
    digest = hashlib.sha256(f"{source_key}\0{original_id}".encode()).hexdigest()[:32]
    return f"legacy-{digest}"


@contextmanager
def _migration_lock(path: Path, timeout_seconds: float = 30.0):
    deadline = time.monotonic() + timeout_seconds
    payload = json.dumps({"pid": os.getpid(), "created_at": time.time()})
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            break
        except FileExistsError:
            owner = _lock_owner(path)
            if owner is not None and not _pid_alive(owner):
                try:
                    path.unlink()
                    continue
                except FileNotFoundError:
                    continue
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"timed out waiting for catalog migration lock: {path}"
                )
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _lock_owner(path: Path) -> int | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return int(value["pid"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


__all__ = ["LegacyCatalogMigrator"]
