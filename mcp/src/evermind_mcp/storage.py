import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from .types_v2 import MemoryRow, BriefingData

logger = logging.getLogger(__name__)


class EmbeddedStorage:
    """SQLite-backed storage with FTS5, optional sqlite-vec, and 6-layer memory model."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._vec_available = False
        # Registry of every SQLite connection opened across all threads.
        # Used by close_all() to release WAL locks on Windows.
        self._all_connections: list[sqlite3.Connection] = []
        self._conn_registry_lock = threading.Lock()
        # Initialise schema on the primary connection
        self._init_schema()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        if not getattr(self._local, "conn", None):
            c = sqlite3.connect(self._db_path, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
            with self._conn_registry_lock:
                self._all_connections.append(c)
        return self._local.conn

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        c = self.conn

        # Try to load sqlite-vec before creating any vec table
        try:
            import sqlite_vec  # type: ignore
            c.enable_load_extension(True)
            sqlite_vec.load(c)
            c.enable_load_extension(False)
            self._vec_available = True
            logger.info("sqlite-vec loaded; vector search enabled")
        except (ImportError, Exception):
            self._vec_available = False
            logger.info("sqlite-vec not available; vector search disabled")

        with self._write_lock:
            c.executescript("""
                -- memories
                CREATE TABLE IF NOT EXISTS memories (
                    id           TEXT    PRIMARY KEY,
                    content      TEXT    NOT NULL,
                    space        TEXT    NOT NULL DEFAULT 'coding:default',
                    layer        TEXT    NOT NULL DEFAULT 'episodic',
                    memory_type  TEXT    NOT NULL DEFAULT 'auto',
                    role         TEXT    NOT NULL DEFAULT 'user',
                    importance   INTEGER NOT NULL DEFAULT 0,
                    tags         TEXT    NOT NULL DEFAULT '[]',
                    meta         TEXT    NOT NULL DEFAULT '{}',
                    created_at   INTEGER NOT NULL,
                    updated_at   INTEGER NOT NULL,
                    expires_at   INTEGER,
                    embedding_ready INTEGER NOT NULL DEFAULT 0
                );

                -- FTS5
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    content,
                    tags,
                    content='memories',
                    content_rowid='rowid',
                    tokenize='unicode61 remove_diacritics 1'
                );

                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content, tags)
                    VALUES (new.rowid, new.content, new.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags)
                    VALUES ('delete', old.rowid, old.content, old.tags);
                    INSERT INTO memories_fts(rowid, content, tags)
                    VALUES (new.rowid, new.content, new.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, tags)
                    VALUES ('delete', old.rowid, old.content, old.tags);
                END;

                -- graph_nodes
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    id         TEXT    PRIMARY KEY,
                    space      TEXT    NOT NULL,
                    node_type  TEXT    NOT NULL,
                    label      TEXT    NOT NULL,
                    meta       TEXT    NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );

                -- graph_edges
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id         TEXT    PRIMARY KEY,
                    space      TEXT    NOT NULL,
                    src_id     TEXT    NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                    dst_id     TEXT    NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
                    edge_type  TEXT    NOT NULL,
                    weight     REAL    NOT NULL DEFAULT 1.0,
                    meta       TEXT    NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );

                -- event_log
                CREATE TABLE IF NOT EXISTS event_log (
                    id         TEXT    PRIMARY KEY,
                    space      TEXT    NOT NULL,
                    event_type TEXT    NOT NULL,
                    memory_id  TEXT,
                    detail     TEXT    NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );

                -- briefing_cache
                CREATE TABLE IF NOT EXISTS briefing_cache (
                    space         TEXT    PRIMARY KEY,
                    recent_json   TEXT    NOT NULL,
                    important_json TEXT   NOT NULL,
                    memory_count  INTEGER NOT NULL DEFAULT 0,
                    updated_at    INTEGER NOT NULL
                );

                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_memories_space      ON memories(space);
                CREATE INDEX IF NOT EXISTS idx_memories_layer      ON memories(layer);
                CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
                CREATE INDEX IF NOT EXISTS idx_memories_expires    ON memories(expires_at) WHERE expires_at IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_event_log_space     ON event_log(space);
            """)
            c.commit()

        # vec0 table (separate, after vec extension is loaded)
        if self._vec_available:
            try:
                with self._write_lock:
                    c.execute("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS memory_vecs USING vec0(
                            memory_rowid INTEGER PRIMARY KEY,
                            embedding FLOAT[512]
                        )
                    """)
                    c.commit()
            except Exception as exc:
                logger.warning("Could not create memory_vecs table: %s", exc)
                self._vec_available = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _row_to_memory(row: sqlite3.Row, score: float = 0.0) -> MemoryRow:
        return MemoryRow(
            id=row["id"],
            content=row["content"],
            space=row["space"],
            layer=row["layer"],
            memory_type=row["memory_type"],
            role=row["role"],
            importance=row["importance"],
            tags=json.loads(row["tags"]),
            meta=json.loads(row["meta"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            embedding_ready=bool(row["embedding_ready"]),
            score=score,
        )

    # ------------------------------------------------------------------
    # Core memory operations
    # ------------------------------------------------------------------

    def insert_memory(
        self,
        space: str,
        content: str,
        layer: str = "episodic",
        memory_type: str = "auto",
        role: str = "user",
        importance: int = 0,
        tags: Optional[list] = None,
        meta: Optional[dict] = None,
    ) -> MemoryRow:
        now = self._now_ms()
        memory_id = str(uuid.uuid4())
        expires_at = now + 24 * 3600 * 1000 if layer == "working" else None
        tags_json = json.dumps(tags or [])
        meta_json = json.dumps(meta or {})

        with self._write_lock:
            self.conn.execute(
                """
                INSERT INTO memories
                    (id, content, space, layer, memory_type, role, importance,
                     tags, meta, created_at, updated_at, expires_at, embedding_ready)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (memory_id, content, space, layer, memory_type, role, importance,
                 tags_json, meta_json, now, now, expires_at),
            )
            self.conn.commit()

        return MemoryRow(
            id=memory_id,
            content=content,
            space=space,
            layer=layer,
            memory_type=memory_type,
            role=role,
            importance=importance,
            tags=tags or [],
            meta=meta or {},
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            embedding_ready=False,
            score=0.0,
        )

    @staticmethod
    def _fts_query(text: str) -> str:
        """Wrap each token in double-quotes so FTS5 treats them as literals.

        Prevents FTS5 from interpreting hyphens as NOT operators or
        bare words as column-filter prefixes (e.g. 'archive-level content'
        would otherwise raise 'no such column: level').
        """
        tokens = [t.strip('"') for t in text.split() if t.strip()]
        return " ".join(f'"{t}"' for t in tokens) if tokens else '""'

    def search_fts(self, query: str, space: str, limit: int = 10) -> list[MemoryRow]:
        now = self._now_ms()
        rows = self.conn.execute(
            """
            SELECT m.*, bm25(memories_fts) AS score
            FROM memories m
            JOIN memories_fts f ON m.rowid = f.rowid
            WHERE memories_fts MATCH ?
              AND m.space = ?
              AND (m.expires_at IS NULL OR m.expires_at > ?)
            ORDER BY score
            LIMIT ?
            """,
            (self._fts_query(query), space, now, limit),
        ).fetchall()
        result = []
        for row in rows:
            # BM25 scores are negative in SQLite FTS5; negate for ascending relevance
            score = -row["score"]
            result.append(self._row_to_memory(row, score=score))
        return result

    def search_vec(
        self, embedding: list[float], space: str, limit: int = 10
    ) -> list[MemoryRow]:
        if not self._vec_available:
            return []
        now = self._now_ms()
        try:
            import struct
            blob = struct.pack(f"{len(embedding)}f", *embedding)
            vec_rows = self.conn.execute(
                """
                SELECT memory_rowid, distance
                FROM memory_vecs
                WHERE embedding MATCH ?
                  AND k = ?
                ORDER BY distance
                """,
                (blob, limit),
            ).fetchall()

            if not vec_rows:
                return []

            rowid_to_dist = {r["memory_rowid"]: r["distance"] for r in vec_rows}
            placeholders = ",".join("?" for _ in rowid_to_dist)
            mem_rows = self.conn.execute(
                f"""
                SELECT m.*
                FROM memories m
                WHERE m.rowid IN ({placeholders})
                  AND m.space = ?
                  AND (m.expires_at IS NULL OR m.expires_at > ?)
                """,
                (*rowid_to_dist.keys(), space, now),
            ).fetchall()

            result = []
            for row in mem_rows:
                distance = rowid_to_dist.get(row["rowid"], 0.0)
                score = 1.0 / (1.0 + distance)
                result.append(self._row_to_memory(row, score=score))
            result.sort(key=lambda r: r.score, reverse=True)
            return result
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)
            return []

    def update_embedding(self, memory_rowid: int, embedding: list[float]) -> None:
        if not self._vec_available:
            return
        import struct
        blob = struct.pack(f"{len(embedding)}f", *embedding)
        with self._write_lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO memory_vecs(memory_rowid, embedding) VALUES (?, ?)",
                (memory_rowid, blob),
            )
            self.conn.execute(
                "UPDATE memories SET embedding_ready=1 WHERE rowid=?",
                (memory_rowid,),
            )
            self.conn.commit()

    def delete_memory(self, memory_id: str) -> bool:
        with self._write_lock:
            cursor = self.conn.execute(
                "DELETE FROM memories WHERE id=?", (memory_id,)
            )
            self.conn.commit()
        return cursor.rowcount > 0

    def get_memory_rowid(self, memory_id: str) -> Optional[int]:
        row = self.conn.execute(
            "SELECT rowid FROM memories WHERE id=?", (memory_id,)
        ).fetchone()
        return row["rowid"] if row else None

    def expire_working_memories(self, space: str) -> int:
        now = self._now_ms()
        with self._write_lock:
            cursor = self.conn.execute(
                """
                DELETE FROM memories
                WHERE space=?
                  AND layer='working'
                  AND expires_at IS NOT NULL
                  AND expires_at < ?
                """,
                (space, now),
            )
            self.conn.commit()
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Briefing cache
    # ------------------------------------------------------------------

    def get_briefing_cache(self, space: str) -> Optional[BriefingData]:
        row = self.conn.execute(
            "SELECT * FROM briefing_cache WHERE space=?", (space,)
        ).fetchone()
        if not row:
            return None
        return BriefingData(
            space=row["space"],
            recent=json.loads(row["recent_json"]),
            important=json.loads(row["important_json"]),
            memory_count=row["memory_count"],
            updated_at=row["updated_at"],
        )

    def refresh_briefing_cache(self, space: str) -> BriefingData:
        now = self._now_ms()

        recent_rows = self.conn.execute(
            """
            SELECT * FROM memories
            WHERE space=? AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY created_at DESC
            LIMIT 8
            """,
            (space, now),
        ).fetchall()

        important_rows = self.conn.execute(
            """
            SELECT * FROM memories
            WHERE space=? AND importance >= 1 AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY importance DESC, updated_at DESC
            LIMIT 5
            """,
            (space, now),
        ).fetchall()

        count_row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM memories WHERE space=?", (space,)
        ).fetchone()
        total = count_row["cnt"] if count_row else 0

        def rows_to_dicts(rows: list) -> list[dict]:
            result = []
            for r in rows:
                result.append({
                    "id": r["id"],
                    "content": r["content"],
                    "space": r["space"],
                    "layer": r["layer"],
                    "memory_type": r["memory_type"],
                    "role": r["role"],
                    "importance": r["importance"],
                    "tags": json.loads(r["tags"]),
                    "meta": json.loads(r["meta"]),
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "expires_at": r["expires_at"],
                    "embedding_ready": bool(r["embedding_ready"]),
                })
            return result

        recent_dicts = rows_to_dicts(recent_rows)
        important_dicts = rows_to_dicts(important_rows)

        with self._write_lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO briefing_cache
                    (space, recent_json, important_json, memory_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (space, json.dumps(recent_dicts), json.dumps(important_dicts), total, now),
            )
            self.conn.commit()

        return BriefingData(
            space=space,
            recent=recent_dicts,
            important=important_dicts,
            memory_count=total,
            updated_at=now,
        )

    # ------------------------------------------------------------------
    # Event log
    # ------------------------------------------------------------------

    def log_event(
        self,
        space: str,
        event_type: str,
        memory_id: Optional[str] = None,
        detail: Optional[dict] = None,
    ) -> None:
        now = self._now_ms()
        event_id = str(uuid.uuid4())
        with self._write_lock:
            self.conn.execute(
                """
                INSERT INTO event_log (id, space, event_type, memory_id, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, space, event_type, memory_id, json.dumps(detail or {}), now),
            )
            self.conn.commit()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self, space: str) -> dict:
        rows = self.conn.execute(
            "SELECT layer, COUNT(*) AS cnt FROM memories WHERE space=? GROUP BY layer",
            (space,),
        ).fetchall()
        by_layer = {r["layer"]: r["cnt"] for r in rows}

        rows = self.conn.execute(
            "SELECT memory_type, COUNT(*) AS cnt FROM memories WHERE space=? GROUP BY memory_type",
            (space,),
        ).fetchall()
        by_type = {r["memory_type"]: r["cnt"] for r in rows}

        agg = self.conn.execute(
            """
            SELECT COUNT(*) AS total_count,
                   MIN(created_at) AS oldest_at,
                   MAX(created_at) AS newest_at
            FROM memories WHERE space=?
            """,
            (space,),
        ).fetchone()

        return {
            "total_count": agg["total_count"] if agg else 0,
            "by_layer": by_layer,
            "by_type": by_type,
            "oldest_at": agg["oldest_at"] if agg else None,
            "newest_at": agg["newest_at"] if agg else None,
        }

    # ------------------------------------------------------------------
    # Dedup helper
    # ------------------------------------------------------------------

    def find_exact(self, content: str, space: str) -> "MemoryRow | None":
        """Return an existing memory with identical content, or None."""
        row = self.conn.execute(
            "SELECT * FROM memories WHERE content=? AND space=?"
            " AND (expires_at IS NULL OR expires_at > ?)",
            (content, space, self._now_ms()),
        ).fetchone()
        return self._row_to_memory(row) if row else None

    def find_similar_fts(
        self, content: str, space: str, threshold: float = 0.1
    ) -> list[MemoryRow]:
        query = content[:50]
        candidates = self.search_fts(query, space, limit=3)
        return [m for m in candidates if m.score > threshold]

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the current thread's SQLite connection."""
        conn = getattr(self._local, "conn", None)
        if conn:
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.execute("PRAGMA journal_mode=DELETE")
                conn.commit()
            except Exception:
                pass
            conn.close()
            self._local.conn = None
            with self._conn_registry_lock:
                try:
                    self._all_connections.remove(conn)
                except ValueError:
                    pass

    def close_all(self) -> None:
        """Close every connection opened across all threads.

        Use this for clean shutdown — especially important on Windows where
        open WAL files prevent temporary-directory cleanup (WinError 32).
        """
        with self._conn_registry_lock:
            conns = list(self._all_connections)
            self._all_connections.clear()

        for c in conns:
            try:
                c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                c.execute("PRAGMA journal_mode=DELETE")
                c.commit()
            except Exception:
                pass
            try:
                c.close()
            except Exception:
                pass
        self._local.conn = None
