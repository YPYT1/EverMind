import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from .types_v2 import MemoryRow, BriefingData

logger = logging.getLogger(__name__)


def _process_for_fts(text: str) -> str:
    """Preprocess text for FTS indexing. Uses jieba for Chinese segmentation if available."""
    try:
        import jieba  # type: ignore
        tokens = list(jieba.cut(text, cut_all=False))
        return " ".join(t for t in tokens if t.strip())
    except ImportError:
        return text


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
            if self._vec_available:
                self._load_vec_extension(c)
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
            self._load_vec_extension(c)
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

                -- FTS5 (self-managed, no external content or triggers)
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    content,
                    tags,
                    tokenize='unicode61 remove_diacritics 1'
                );

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

                -- _meta
                CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT);

                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_memories_space      ON memories(space);
                CREATE INDEX IF NOT EXISTS idx_memories_layer      ON memories(layer);
                CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
                CREATE INDEX IF NOT EXISTS idx_memories_expires    ON memories(expires_at) WHERE expires_at IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_event_log_space     ON event_log(space);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_nodes_unique ON graph_nodes(space, node_type, label);
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
    def _load_vec_extension(conn: sqlite3.Connection) -> None:
        import sqlite_vec  # type: ignore

        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        finally:
            conn.enable_load_extension(False)

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
            # Manually insert into FTS with jieba preprocessing
            inserted_rowid = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            processed_content = _process_for_fts(content)
            self.conn.execute(
                "INSERT INTO memories_fts(rowid, content, tags) VALUES (?, ?, ?)",
                (inserted_rowid, processed_content, tags_json)
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

    # ------------------------------------------------------------------
    # _meta helpers
    # ------------------------------------------------------------------

    def get_meta(self, key: str) -> "str | None":
        row = self.conn.execute(
            "SELECT value FROM _meta WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._write_lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)",
                (key, value),
            )
            self.conn.commit()

    def check_embed_dim(self, dim: int) -> bool:
        stored_dim = self.get_meta("embed_dim")
        if stored_dim is None:
            self.set_meta("embed_dim", str(dim))
            return True
        if int(stored_dim) == dim:
            return True
        logger.warning(
            "Embedding dimension mismatch: stored=%s, current=%s. Vector search disabled.",
            stored_dim,
            dim,
        )
        return False

    # ------------------------------------------------------------------
    # List memories
    # ------------------------------------------------------------------

    def list_memories(
        self,
        space: str,
        layer: str = None,
        tags: list = None,
        limit: int = 20,
    ) -> "list[MemoryRow]":
        now = self._now_ms()
        params: list = [space]
        sql = "SELECT * FROM memories WHERE space=?"
        if layer is not None:
            sql += " AND layer=?"
            params.append(layer)
        if tags is not None and len(tags) > 0:
            tag_clauses = " OR ".join(
                "tags LIKE ?" for _ in tags
            )
            sql += f" AND ({tag_clauses})"
            for tag in tags:
                params.append(f'%"{tag}"%')
        sql += " AND (expires_at IS NULL OR expires_at > ?)"
        params.append(now)
        sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def search_fts(self, query: str, space: str, limit: int = 10, layer: str = None, tags: list = None) -> list[MemoryRow]:
        now = self._now_ms()
        processed_query = _process_for_fts(query)
        params: list = [self._fts_query(processed_query), space]
        extra = ""
        if layer is not None:
            extra += " AND m.layer=?"
            params.append(layer)
        if tags is not None and len(tags) > 0:
            tag_clauses = " OR ".join("m.tags LIKE ?" for _ in tags)
            extra += f" AND ({tag_clauses})"
            for tag in tags:
                params.append(f'%"{tag}"%')
        params.append(now)
        params.append(limit)
        rows = self.conn.execute(
            f"""
            SELECT m.*, bm25(memories_fts) AS score
            FROM memories m
            JOIN memories_fts f ON m.rowid = f.rowid
            WHERE memories_fts MATCH ?
              AND m.space = ?
              {extra}
              AND (m.expires_at IS NULL OR m.expires_at > ?)
            ORDER BY score
            LIMIT ?
            """,
            params,
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
                SELECT m.rowid AS rowid, m.*
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
            # Remove from FTS before deleting the row (need the rowid while it exists)
            row = self.conn.execute(
                "SELECT rowid, content, tags FROM memories WHERE id=?", (memory_id,)
            ).fetchone()
            if row:
                self.conn.execute(
                    "DELETE FROM memories_fts WHERE rowid=?",
                    (row["rowid"],)
                )
                if self._vec_available:
                    self.conn.execute(
                        "DELETE FROM memory_vecs WHERE memory_rowid=?",
                        (row["rowid"],),
                    )
                self._delete_graph_edges_for_memory(memory_id)
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

    def get_memory(self, memory_id: str) -> "MemoryRow | None":
        row = self.conn.execute(
            "SELECT * FROM memories WHERE id=?", (memory_id,)
        ).fetchone()
        return self._row_to_memory(row) if row else None

    def expire_working_memories(self, space: str) -> int:
        now = self._now_ms()
        with self._write_lock:
            rows = self.conn.execute(
                """
                SELECT rowid, id FROM memories
                WHERE space=?
                  AND layer='working'
                  AND expires_at IS NOT NULL
                  AND expires_at < ?
                """,
                (space, now),
            ).fetchall()
            for row in rows:
                self.conn.execute("DELETE FROM memories_fts WHERE rowid=?", (row["rowid"],))
                if self._vec_available:
                    self.conn.execute(
                        "DELETE FROM memory_vecs WHERE memory_rowid=?",
                        (row["rowid"],),
                    )
                self._delete_graph_edges_for_memory(row["id"])
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

    def refresh_briefing_cache(self, space: str, recent_limit: int = 8, important_limit: int = 5) -> BriefingData:
        now = self._now_ms()

        recent_rows = self.conn.execute(
            """
            SELECT * FROM memories
            WHERE space=? AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (space, now, recent_limit),
        ).fetchall()

        important_rows = self.conn.execute(
            """
            SELECT * FROM memories
            WHERE space=? AND importance >= 1 AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
            """,
            (space, now, important_limit),
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

    def count_embeddings(self, space: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM memories WHERE space=? AND embedding_ready=1",
            (space,),
        ).fetchone()
        return row["cnt"] if row else 0

    def count_fts_entries(self, space: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM memories m
            JOIN memories_fts f ON m.rowid = f.rowid
            WHERE m.space=?
            """,
            (space,),
        ).fetchone()
        return row["cnt"] if row else 0

    def count_expired_working(self, space: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM memories
            WHERE space=?
              AND layer='working'
              AND expires_at IS NOT NULL
              AND expires_at < ?
            """,
            (space, self._now_ms()),
        ).fetchone()
        return row["cnt"] if row else 0

    def count_exact_duplicates(self, space: str) -> int:
        rows = self.conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM (
                SELECT content
                FROM memories
                WHERE space=?
                GROUP BY content
                HAVING COUNT(*) > 1
            )
            """,
            (space,),
        ).fetchone()
        return rows["cnt"] if rows else 0

    def get_graph_stats(self, space: str) -> dict:
        node_row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM graph_nodes WHERE space=?",
            (space,),
        ).fetchone()
        edge_row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM graph_edges WHERE space=?",
            (space,),
        ).fetchone()
        total_row = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM memories WHERE space=?",
            (space,),
        ).fetchone()
        try:
            linked_row = self.conn.execute(
                """
                SELECT COUNT(DISTINCT json_extract(meta, '$.memory_id')) AS cnt
                FROM graph_edges
                WHERE space=?
                  AND edge_type='MENTIONED_IN'
                  AND json_extract(meta, '$.memory_id') IS NOT NULL
                """,
                (space,),
            ).fetchone()
            linked = linked_row["cnt"] if linked_row else 0
        except sqlite3.DatabaseError:
            linked = self._count_graph_memory_ids_without_json(space)
        total = total_row["cnt"] if total_row else 0
        return {
            "graph_node_count": node_row["cnt"] if node_row else 0,
            "graph_edge_count": edge_row["cnt"] if edge_row else 0,
            "graph_linked_memory_count": linked,
            "graph_coverage_percent": round((linked / total) * 100, 2)
            if total
            else 100.0,
        }

    def _count_graph_memory_ids_without_json(self, space: str) -> int:
        rows = self.conn.execute(
            """
            SELECT meta FROM graph_edges
            WHERE space=? AND edge_type='MENTIONED_IN'
            """,
            (space,),
        ).fetchall()
        linked_ids = set()
        for row in rows:
            try:
                memory_id = json.loads(row["meta"]).get("memory_id")
                if memory_id:
                    linked_ids.add(memory_id)
            except Exception:
                continue
        return len(linked_ids)

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

    def update_memory_content(self, memory_id: str, new_content: str) -> None:
        """Update the content of an existing memory (used by fuzzy dedup merge)."""
        self.update_memory(memory_id, content=new_content)

    def update_memory(
        self,
        memory_id: str,
        *,
        content: str | None = None,
        layer: str | None = None,
        memory_type: str | None = None,
        importance: int | None = None,
        tags: list | None = None,
        meta: dict | None = None,
    ) -> "MemoryRow | None":
        """Update an existing memory and keep FTS/vector/graph state consistent."""
        now = self._now_ms()
        with self._write_lock:
            row = self.conn.execute(
                "SELECT rowid, * FROM memories WHERE id=?", (memory_id,)
            ).fetchone()
            if not row:
                return None

            rowid = row["rowid"]
            old_content = row["content"]
            new_content = old_content if content is None else content
            new_layer = row["layer"] if layer is None else layer
            new_type = row["memory_type"] if memory_type is None else memory_type
            new_importance = row["importance"] if importance is None else importance
            new_tags = json.loads(row["tags"]) if tags is None else tags
            new_meta = json.loads(row["meta"]) if meta is None else meta
            tags_json = json.dumps(new_tags)
            meta_json = json.dumps(new_meta)
            old_layer = row["layer"]
            if new_layer == "working":
                expires_at = (
                    row["expires_at"]
                    if old_layer == "working" and row["expires_at"] is not None
                    else now + 24 * 3600 * 1000
                )
            else:
                expires_at = None
            content_changed = new_content != old_content

            self.conn.execute(
                """
                UPDATE memories
                SET content=?, layer=?, memory_type=?, importance=?, tags=?, meta=?,
                    updated_at=?, expires_at=?, embedding_ready=?
                WHERE id=?
                """,
                (
                    new_content,
                    new_layer,
                    new_type,
                    new_importance,
                    tags_json,
                    meta_json,
                    now,
                    expires_at,
                    0 if content_changed else row["embedding_ready"],
                    memory_id,
                ),
            )
            self.conn.execute("DELETE FROM memories_fts WHERE rowid=?", (rowid,))
            self.conn.execute(
                "INSERT INTO memories_fts(rowid, content, tags) VALUES (?, ?, ?)",
                (rowid, _process_for_fts(new_content), tags_json),
            )
            if content_changed and self._vec_available:
                self.conn.execute(
                    "DELETE FROM memory_vecs WHERE memory_rowid=?",
                    (rowid,),
                )
            if content_changed:
                self._delete_graph_edges_for_memory(memory_id)
            self.conn.commit()

        updated = self.conn.execute(
            "SELECT * FROM memories WHERE id=?", (memory_id,)
        ).fetchone()
        return self._row_to_memory(updated) if updated else None

    def find_similar_fts(
        self, content: str, space: str, threshold: float = 0.1
    ) -> list[MemoryRow]:
        query = content[:50]
        candidates = self.search_fts(query, space, limit=3)
        return [m for m in candidates if m.score > threshold]

    # ------------------------------------------------------------------
    # Graph layer
    # ------------------------------------------------------------------

    def upsert_graph_node(self, space: str, node_type: str, label: str, meta: dict = {}) -> str:
        now = self._now_ms()
        existing = self.conn.execute(
            "SELECT id FROM graph_nodes WHERE space=? AND node_type=? AND label=?",
            (space, node_type, label),
        ).fetchone()
        if existing:
            return existing["id"]
        node_id = str(uuid.uuid4())
        with self._write_lock:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO graph_nodes (id, space, node_type, label, meta, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (node_id, space, node_type, label, json.dumps(meta), now),
            )
            self.conn.commit()
        # Re-fetch in case INSERT OR IGNORE lost a race
        row = self.conn.execute(
            "SELECT id FROM graph_nodes WHERE space=? AND node_type=? AND label=?",
            (space, node_type, label),
        ).fetchone()
        return row["id"] if row else node_id

    def add_graph_edge(
        self,
        space: str,
        src_id: str,
        dst_id: str,
        edge_type: str,
        weight: float = 1.0,
        meta: dict = {},
    ) -> str:
        now = self._now_ms()
        edge_id = str(uuid.uuid4())
        with self._write_lock:
            self.conn.execute(
                """
                INSERT INTO graph_edges (id, space, src_id, dst_id, edge_type, weight, meta, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (edge_id, space, src_id, dst_id, edge_type, weight, json.dumps(meta), now),
            )
            self.conn.commit()
        return edge_id

    def link_memory_to_entities(self, memory_id: str, space: str, entities: list) -> None:
        for entity in entities:
            node_id = self.upsert_graph_node(space, "entity", entity)
            self.add_graph_edge(
                space=space,
                src_id=node_id,
                dst_id=node_id,  # self-ref placeholder; real target stored in meta
                edge_type="MENTIONED_IN",
                meta={"memory_id": memory_id},
            )

    def _delete_graph_edges_for_memory(self, memory_id: str) -> None:
        try:
            self.conn.execute(
                "DELETE FROM graph_edges WHERE json_extract(meta, '$.memory_id')=?",
                (memory_id,),
            )
        except sqlite3.DatabaseError:
            rows = self.conn.execute("SELECT id, meta FROM graph_edges").fetchall()
            for row in rows:
                try:
                    if json.loads(row["meta"]).get("memory_id") == memory_id:
                        self.conn.execute(
                            "DELETE FROM graph_edges WHERE id=?",
                            (row["id"],),
                        )
                except Exception:
                    continue

    def search_graph(self, space: str, entity_label: str, limit: int = 10) -> list:
        entity_label = entity_label.strip()
        if not entity_label:
            return []
        normalized = entity_label.replace("\\", "/")
        patterns = [entity_label, normalized, normalized.lower()]
        if "/" in normalized:
            patterns.append(Path(normalized).name)

        nodes = self.conn.execute(
            """
            SELECT * FROM graph_nodes
            WHERE space=?
              AND (
                lower(label) LIKE lower(?)
                OR lower(label) LIKE lower(?)
                OR lower(label) LIKE lower(?)
                OR lower(label) LIKE lower(?)
              )
            ORDER BY
              CASE WHEN lower(label)=lower(?) THEN 0 ELSE 1 END,
              length(label)
            LIMIT ?
            """,
            (
                space,
                f"%{patterns[0]}%",
                f"%{patterns[1]}%",
                f"%{patterns[2]}%",
                f"%{patterns[-1]}%",
                entity_label,
                max(limit * 3, 10),
            ),
        ).fetchall()
        results = []
        seen: set[str] = set()
        for node in nodes:
            edges = self.conn.execute(
                """
                SELECT * FROM graph_edges
                WHERE src_id=? AND edge_type='MENTIONED_IN'
                LIMIT ?
                """,
                (node["id"], limit),
            ).fetchall()
            for edge in edges:
                edge_meta = json.loads(edge["meta"])
                memory_id = edge_meta.get("memory_id")
                if not memory_id:
                    continue
                mem_row = self.conn.execute(
                    "SELECT * FROM memories WHERE id=?", (memory_id,)
                ).fetchone()
                if mem_row:
                    if mem_row["id"] in seen:
                        continue
                    seen.add(mem_row["id"])
                    results.append({
                        "entity": node["label"],
                        "memory": self._row_to_memory(mem_row).to_dict(),
                    })
        return results[:limit]

    def extract_entities_from_content(self, content: str) -> list:
        found: list = []
        normalized_content = content.replace("\\", "/")

        def add_path_aliases(path_text: str) -> None:
            normalized_path = path_text.replace("\\", "/").strip("`'\".,;:()[]{}")
            found.append(normalized_path)
            path = Path(normalized_path)
            if path.name:
                found.append(path.name)
            parts = [part for part in normalized_path.split("/") if part]
            if len(parts) >= 2:
                found.append("/".join(parts[-2:]))
            for part in parts[:-1]:
                if len(part) >= 3:
                    found.append(part)

        # File paths plus useful aliases such as service.py and publish/service.py.
        for m in re.finditer(
            r"(?<!\w)[\w./\\-]+\.(?:py|ts|js|go|rs|java|cpp|h|json|yaml|toml|md)\b",
            normalized_content,
        ):
            add_path_aliases(m.group(0))

        # CamelCase identifiers
        for m in re.finditer(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", content):
            found.append(m.group(0))

        # module/class/function/def/import names
        for m in re.finditer(
            r"(?:module|class|function|def|import)\s+([\w_./-]+)", content
        ):
            found.append(m.group(1))

        # snake_case identifiers and common two-word module descriptions
        for m in re.finditer(r"\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\b", content):
            found.append(m.group(0))
        for m in re.finditer(
            r"\b([a-z][a-z0-9-]+(?:\s+(?:runner|service|module|flow|pipeline|action|worker|test|command)))\b",
            content.lower(),
        ):
            found.append(m.group(1))

        technical_terms = (
            "greenlet",
            "playwright",
            "pytest",
            "aria",
            "role",
            "bitbrowser",
            "sqlite-vec",
            "qwen3",
            "deepseek",
            "siliconflow",
            "rerank",
            "reranker",
            "embedding",
            "embeddings",
            "fts",
            "bm25",
            "jieba",
            "youtube",
            "mcp",
            "cursor",
        )
        lower_content = content.lower()
        for term in technical_terms:
            if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", lower_content):
                found.append(term)

        chinese_terms = (
            "发布流程",
            "文本选择器",
            "中文",
            "索引",
            "重建",
            "并发",
            "会话",
            "生命周期",
            "测试命令",
            "运行命令",
            "决策",
            "禁止",
            "必须",
            "错误",
            "异常",
            "流程",
        )
        for term in chinese_terms:
            if term in content:
                found.append(term)

        # Deduplicate case-insensitively, filter short, keep enough context.
        seen: set = set()
        result: list = []
        for entity in found:
            cleaned = str(entity).strip("`'\".,;:()[]{}")
            if len(cleaned) < 2:
                continue
            key = cleaned.lower()
            if key not in seen:
                seen.add(key)
                result.append(cleaned)
            if len(result) >= 30:
                break
        return result

    def reindex_graph(self, space: str | None = None) -> dict:
        """Rebuild graph nodes/edges from current memory content."""
        params: tuple = (space,) if space else ()
        where = "WHERE space=?" if space else ""
        rows = self.conn.execute(
            f"SELECT id, content, space FROM memories {where}",
            params,
        ).fetchall()
        with self._write_lock:
            if space:
                self.conn.execute("DELETE FROM graph_edges WHERE space=?", (space,))
                self.conn.execute("DELETE FROM graph_nodes WHERE space=?", (space,))
            else:
                self.conn.execute("DELETE FROM graph_edges")
                self.conn.execute("DELETE FROM graph_nodes")
            self.conn.commit()

        linked = 0
        edge_count_before = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM graph_edges"
        ).fetchone()["cnt"]
        for row in rows:
            entities = self.extract_entities_from_content(row["content"])
            if entities:
                linked += 1
                self.link_memory_to_entities(row["id"], row["space"], entities)
        edge_count_after = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM graph_edges"
        ).fetchone()["cnt"]
        return {
            "graph_reindexed": len(rows),
            "graph_linked_memories": linked,
            "graph_edges_created": edge_count_after - edge_count_before,
            "spaces": sorted({row["space"] for row in rows}),
        }

    # ------------------------------------------------------------------
    # Export / compact / utility
    # ------------------------------------------------------------------

    def export_memories(self, space: str, layer: str = None) -> list:
        sql = "SELECT * FROM memories WHERE space=? AND (expires_at IS NULL OR expires_at > ?)"
        params = [space, self._now_ms()]
        if layer:
            sql += " AND layer=?"
            params.append(layer)
        sql += (
            " ORDER BY CASE layer"
            " WHEN 'archive' THEN 0"
            " WHEN 'semantic' THEN 1"
            " WHEN 'procedural' THEN 2"
            " WHEN 'episodic' THEN 3"
            " ELSE 4 END,"
            " importance DESC, updated_at DESC"
        )
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def compact_episodic(self, space: str, older_than_days: int = 30) -> dict:
        cutoff_ms = self._now_ms() - (older_than_days * 24 * 3600 * 1000)
        old_rows = self.conn.execute(
            "SELECT * FROM memories WHERE space=? AND layer='episodic' AND created_at < ?",
            (space, cutoff_ms)
        ).fetchall()
        if not old_rows:
            return {"summarized": 0, "created_id": None}
        old_memories = [self._row_to_memory(r) for r in old_rows]
        summary_parts = [f"- {m.content}" for m in old_memories[:50]]
        summary = (
            f"Compacted {len(old_memories)} episodic memories"
            f" (older than {older_than_days}d):\n"
            + "\n".join(summary_parts)
        )
        summary_memory = self.insert_memory(
            content=summary,
            space=space,
            layer="semantic",
            memory_type="semantic",
            importance=1,
            tags=["compacted"],
            role="system",
        )
        summary_entities = self.extract_entities_from_content(summary)
        if summary_entities:
            self.link_memory_to_entities(summary_memory.id, space, summary_entities)
        ids = [m.id for m in old_memories]
        placeholders = ",".join("?" * len(ids))
        with self._write_lock:
            # Remove FTS entries for deleted rows before deleting the main rows
            for m in old_memories:
                row = self.conn.execute(
                    "SELECT rowid, content, tags FROM memories WHERE id=?", (m.id,)
                ).fetchone()
                if row:
                    self.conn.execute("DELETE FROM memories_fts WHERE rowid=?", (row["rowid"],))
                    if self._vec_available:
                        self.conn.execute(
                            "DELETE FROM memory_vecs WHERE memory_rowid=?",
                            (row["rowid"],),
                        )
                    self._delete_graph_edges_for_memory(m.id)
            self.conn.execute(f"DELETE FROM memories WHERE id IN ({placeholders})", ids)
            self.conn.commit()
        return {"summarized": len(old_memories), "created_id": summary_memory.id}

    def reindex_fts(self, space: str | None = None) -> dict:
        """Rebuild FTS entries with the current tokenizer/preprocessor."""
        params: tuple = (space,) if space else ()
        where = "WHERE space=?" if space else ""
        rows = self.conn.execute(
            f"SELECT rowid, content, tags, space FROM memories {where}",
            params,
        ).fetchall()
        with self._write_lock:
            if space:
                rowids = [row["rowid"] for row in rows]
                if rowids:
                    placeholders = ",".join("?" for _ in rowids)
                    self.conn.execute(
                        f"DELETE FROM memories_fts WHERE rowid IN ({placeholders})",
                        rowids,
                    )
            else:
                self.conn.execute("DELETE FROM memories_fts")
            for row in rows:
                self.conn.execute(
                    "INSERT INTO memories_fts(rowid, content, tags) VALUES (?, ?, ?)",
                    (row["rowid"], _process_for_fts(row["content"]), row["tags"]),
                )
            self.conn.commit()
        spaces = sorted({row["space"] for row in rows})
        return {"reindexed": len(rows), "spaces": spaces}

    def list_tags(self, space: str) -> list:
        rows = self.conn.execute(
            "SELECT DISTINCT tags FROM memories WHERE space=? AND tags != '[]'", (space,)
        ).fetchall()
        all_tags: set = set()
        for row in rows:
            try:
                tags = json.loads(row[0])
                if isinstance(tags, list):
                    all_tags.update(t for t in tags if t)
            except Exception:
                pass
        return sorted(all_tags)

    def search_fts_multi(self, query: str, spaces: list, limit: int = 10) -> list:
        all_results = []
        for space in spaces:
            results = self.search_fts(query, space, limit=limit)
            all_results.extend(results)
        seen: set = set()
        deduped = []
        for r in sorted(all_results, key=lambda x: x.score, reverse=True):
            if r.id not in seen:
                seen.add(r.id)
                deduped.append(r)
        return deduped[:limit]

    def list_spaces(self) -> list:
        rows = self.conn.execute("SELECT DISTINCT space FROM memories").fetchall()
        return sorted(r[0] for r in rows)

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
