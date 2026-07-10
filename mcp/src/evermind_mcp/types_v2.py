"""Shared data types for EverMind v2."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


MEMORY_TYPES = ("episodic", "semantic", "procedural", "decision", "bug", "preference", "auto")


@dataclass
class MemoryRow:
    id: str
    content: str
    space: str
    memory_type: str = "auto"
    layer: str = "episodic"          # working/episodic/semantic/procedural/archive
    role: str = "user"
    created_at: int = 0
    updated_at: int = 0
    importance: int = 0
    tags: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    expires_at: Optional[int] = None
    state: str = "active"
    valid_from: Optional[int] = None
    valid_to: Optional[int] = None
    supersedes_id: Optional[str] = None
    embedding_ready: bool = False
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "space": self.space,
            "layer": self.layer,
            "type": self.memory_type,
            "role": self.role,
            "importance": self.importance,
            "tags": self.tags,
            "meta": self.meta,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "state": self.state,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "supersedes_id": self.supersedes_id,
            "score": round(self.score, 4),
        }


@dataclass
class SearchResult:
    memories: list[MemoryRow]
    mode_used: str
    total_found: int


@dataclass
class BriefingData:
    space: str
    recent: list[MemoryRow]
    important: list[MemoryRow]
    memory_count: int
    updated_at: int

    def to_dict(self) -> dict:
        def _item(m) -> dict:
            # Items may be MemoryRow objects or plain dicts (after JSON round-trip)
            return m.to_dict() if hasattr(m, "to_dict") else m

        return {
            "space": self.space,
            "memory_count": self.memory_count,
            "recent": [_item(m) for m in self.recent],
            "important": [_item(m) for m in self.important],
            "updated_at": self.updated_at,
        }
