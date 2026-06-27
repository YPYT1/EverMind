"""EverOS local API adapter.

This adapter presents the small EverMindCloudClient-shaped surface used by
MemoryService while translating calls to EverOS /api/v1/memory/*.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

import httpx

from . import config
from .cloud_client import EverMindMCPError
from .space_catalog_service import from_group_id


_SEARCH_METHOD_MAP = {
    "keyword": "keyword",
    "vector": "vector",
    "hybrid": "hybrid",
    "rrf": "hybrid",
    "agentic": "agentic",
    "auto": "hybrid",
}

_FETCH_TYPE_MAP = {
    "profile": "profile",
    "episodic_memory": "episode",
    "event_log": "episode",
    "foresight": "episode",
    "agent_case": "agent_case",
    "agent_skill": "agent_skill",
}


class EverOSClient:
    """Async client for a local EverOS server."""

    def __init__(
        self,
        base_url: str | None = None,
        user_id: str | None = None,
        timeout: float | None = None,
    ):
        self._base_url = (base_url or config.EVEROS_BASE_URL).rstrip("/")
        self._user_id = user_id or config.EVERMIND_MCP_USER_ID
        self._timeout = timeout if timeout is not None else config.EVEROS_TIMEOUT_SECONDS
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EverOSClient":
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    @property
    def user_id(self) -> str:
        return self._user_id

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            timeout = httpx.Timeout(
                connect=self._timeout,
                read=self._timeout,
                write=self._timeout,
                pool=self._timeout,
            )
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        client = await self._get_client()
        try:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                headers={"Content-Type": "application/json"},
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise EverMindMCPError(
                f"EverOS request timed out: {exc}",
                code="UPSTREAM_UNAVAILABLE",
            ) from exc
        except httpx.RequestError as exc:
            raise EverMindMCPError(
                f"Cannot reach EverOS at {self._base_url}: {exc}",
                code="UPSTREAM_UNAVAILABLE",
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise EverMindMCPError(
                "EverOS returned invalid JSON response",
                code="UPSTREAM_ERROR",
                status_code=response.status_code,
            ) from exc

        if response.status_code >= 400:
            err = body.get("error") if isinstance(body, dict) else None
            message = ""
            code = "UPSTREAM_ERROR"
            if isinstance(err, dict):
                message = str(err.get("message") or "")
                code = str(err.get("code") or code)
            if not message:
                message = response.text[:500]
            raise EverMindMCPError(message, code=code, status_code=response.status_code)

        if not isinstance(body, dict):
            raise EverMindMCPError(
                "EverOS returned non-object JSON response",
                code="UPSTREAM_ERROR",
                status_code=response.status_code,
            )
        return body

    @staticmethod
    def _space_from_group(group_id: str | None) -> str:
        if not isinstance(group_id, str) or not group_id.strip():
            return "default:default"
        space_id = from_group_id(group_id.strip())
        return space_id or group_id.strip()

    @staticmethod
    def _scope_from_group(group_id: str | None) -> tuple[str, str]:
        space_id = EverOSClient._space_from_group(group_id)
        if ":" in space_id:
            app_id, project_id = space_id.split(":", 1)
        else:
            app_id, project_id = "default", space_id
        return EverOSClient._safe_scope_id(app_id), EverOSClient._safe_scope_id(project_id)

    @staticmethod
    def _is_agent_scope(app_id: str) -> bool:
        return app_id == "agent"

    def _owner_for_scope(
        self,
        *,
        app_id: str,
        project_id: str,
        user_id: str | None,
        agent_track: bool = False,
    ) -> tuple[str, str]:
        if agent_track or self._is_agent_scope(app_id):
            return "agent_id", project_id
        return "user_id", self._safe_scope_id(user_id or self._user_id)

    @staticmethod
    def _safe_scope_id(value: str) -> str:
        cleaned = []
        for char in value.strip() or "default":
            if char.isalnum() or char in {"_", ".", "-"}:
                cleaned.append(char)
            else:
                cleaned.append("-")
        result = "".join(cleaned).strip(".")
        return result or "default"

    @staticmethod
    def _group_from_scope(app_id: str, project_id: str) -> str:
        if app_id == "default" and project_id == "default":
            return "space::default:default"
        return f"space::{app_id}:{project_id}"

    @staticmethod
    def _timestamp_ms(create_time: str | None) -> int:
        if isinstance(create_time, str) and create_time.strip():
            raw = create_time.strip()
            normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                parsed = datetime.now(timezone.utc)
        else:
            parsed = datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)

    @staticmethod
    def _normalize_group_ids(
        group_ids: str | Iterable[str] | None,
        group_id: str | None,
    ) -> list[str]:
        raw = group_ids if group_ids is not None else group_id
        if raw is None:
            return ["space::default:default"]
        if isinstance(raw, str):
            return [raw]
        return [item for item in raw if isinstance(item, str) and item.strip()]

    async def health(self) -> dict:
        return await self._request("GET", "/health")

    async def add_message(
        self,
        group_id: str,
        content: str,
        *,
        sender: str | None = None,
        sender_name: str | None = None,
        role: str = "user",
        flush: bool = False,
        message_id: str | None = None,
        create_time: str | None = None,
        group_name: str | None = None,
        refer_list: list[str] | None = None,
    ) -> dict:
        del group_name, refer_list
        app_id, project_id = self._scope_from_group(group_id)
        session_id = message_id or f"msg_{uuid4().hex[:12]}"
        if self._is_agent_scope(app_id):
            sender_id = project_id
            message_role = "assistant" if role == "user" else role
            sender_display_name = sender_name or sender or project_id
        else:
            sender_id = sender or self._user_id
            message_role = role
            sender_display_name = sender_name or sender_id
        payload = {
            "session_id": session_id,
            "app_id": app_id,
            "project_id": project_id,
            "messages": [
                {
                    "sender_id": self._safe_scope_id(sender_id),
                    "sender_name": sender_display_name,
                    "role": message_role,
                    "timestamp": self._timestamp_ms(create_time),
                    "content": content,
                }
            ],
        }
        add_result = await self._request(
            "POST",
            "/api/v1/memory/add",
            json=payload,
        )

        status = add_result.get("data", {}).get("status", "accumulated")
        if flush:
            flush_result = await self._request(
                "POST",
                "/api/v1/memory/flush",
                json={
                    "session_id": session_id,
                    "app_id": app_id,
                    "project_id": project_id,
                },
            )
            status = flush_result.get("data", {}).get("status", status)

        return {
            "status": "completed" if status in {"extracted", "no_extraction"} else status,
            "request_id": add_result.get("request_id", session_id),
            "message_id": session_id,
        }

    async def fetch_memories(
        self,
        group_ids: str | Iterable[str] | None = None,
        *,
        group_id: str | None = None,
        memory_type: str = "episodic_memory",
        user_id: str | None = None,
        limit: int = 40,
        offset: int = 0,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict:
        group = self._normalize_group_ids(group_ids, group_id)[0]
        app_id, project_id = self._scope_from_group(group)
        mapped_type = _FETCH_TYPE_MAP.get(memory_type, "episode")
        owner_field, owner_id = self._owner_for_scope(
            app_id=app_id,
            project_id=project_id,
            user_id=user_id,
            agent_track=mapped_type.startswith("agent_"),
        )
        page_size = max(1, min(int(limit), 100))
        page = (max(0, int(offset)) // page_size) + 1
        filters = self._build_time_filters(start_time, end_time)
        response = await self._request(
            "POST",
            "/api/v1/memory/get",
            json={
                owner_field: self._safe_scope_id(owner_id),
                "app_id": app_id,
                "project_id": project_id,
                "memory_type": mapped_type,
                "page": page,
                "page_size": page_size,
                "filters": filters,
            },
        )
        data = response.get("data", {})
        memories = self._items_for_type(data, mapped_type)
        return {
            "result": {
                "memories": [
                    self._map_item(item, memory_type=memory_type, app_id=app_id, project_id=project_id)
                    for item in memories
                ],
                "count": data.get("count", len(memories)),
                "total_count": data.get("total_count", len(memories)),
            }
        }

    async def search_memories(
        self,
        query: str,
        group_ids: str | Iterable[str] | None = None,
        *,
        group_id: str | None = None,
        retrieve_method: str = "hybrid",
        memory_types: list[str] | None = None,
        top_k: int = 10,
        user_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        current_time: str | None = None,
        radius: float | None = None,
        include_metadata: bool | None = None,
    ) -> dict:
        del current_time, include_metadata
        groups = self._normalize_group_ids(group_ids, group_id)
        responses: list[dict] = []
        for group in groups:
            responses.append(
                await self._search_one(
                    query=query,
                    group_id=group,
                    retrieve_method=retrieve_method,
                    memory_types=memory_types,
                    top_k=top_k,
                    user_id=user_id,
                    start_time=start_time,
                    end_time=end_time,
                    radius=radius,
                )
            )

        if len(responses) == 1:
            return responses[0]

        merged: list[dict] = []
        for response in responses:
            memories = response.get("result", {}).get("memories", [])
            if isinstance(memories, list):
                merged.extend(item for item in memories if isinstance(item, dict))
        merged.sort(key=lambda item: item.get("score") or 0, reverse=True)
        if top_k != -1:
            merged = merged[: max(0, int(top_k))]
        return {"result": {"memories": merged, "pending_messages": []}}

    async def _search_one(
        self,
        *,
        query: str,
        group_id: str,
        retrieve_method: str,
        memory_types: list[str] | None,
        top_k: int,
        user_id: str | None,
        start_time: str | None,
        end_time: str | None,
        radius: float | None,
    ) -> dict:
        app_id, project_id = self._scope_from_group(group_id)
        search_agent = bool(memory_types) and all(
            item in {"agent_case", "agent_skill"} for item in memory_types
        )
        owner_field, owner_id = self._owner_for_scope(
            app_id=app_id,
            project_id=project_id,
            user_id=user_id,
            agent_track=search_agent,
        )
        is_agent_search = owner_field == "agent_id"
        payload: dict = {
            owner_field: self._safe_scope_id(owner_id),
            "app_id": app_id,
            "project_id": project_id,
            "query": query,
            "method": _SEARCH_METHOD_MAP.get(retrieve_method, "hybrid"),
            "top_k": top_k,
            "include_profile": bool(
                not is_agent_search
                and (memory_types is None or "profile" in memory_types)
            ),
            "filters": self._build_time_filters(start_time, end_time),
        }
        if radius is not None:
            payload["radius"] = radius

        response = await self._request("POST", "/api/v1/memory/search", json=payload)
        data = response.get("data", {})
        mapped = []
        for kind in ("episodes", "profiles", "agent_cases", "agent_skills"):
            for item in data.get(kind, []) or []:
                if isinstance(item, dict):
                    mapped.append(self._map_item(item, app_id=app_id, project_id=project_id))
        return {"result": {"memories": mapped, "pending_messages": []}}

    async def get_request_status(self, request_id: str) -> dict:
        if not isinstance(request_id, str) or not request_id.strip():
            raise EverMindMCPError("request_id is required", code="INVALID_INPUT")
        return {
            "success": True,
            "found": True,
            "message": "EverOS local writes are synchronous to Markdown; search index may lag.",
            "data": {"request_id": request_id.strip(), "status": "completed"},
        }

    async def set_conversation_metadata(self, **kwargs) -> dict:
        return {"result": dict(kwargs)}

    async def update_conversation_metadata(self, **kwargs) -> dict:
        return {"result": dict(kwargs)}

    async def get_conversation_metadata(self, group_id: str) -> dict:
        return {"result": {"group_id": group_id, "description": ""}}

    async def delete_memories(self, **kwargs) -> dict:
        del kwargs
        raise EverMindMCPError(
            "EverOS backend does not support MCP forget in V1; delete or edit Markdown manually after review.",
            code="UNSUPPORTED_OPERATION",
        )

    async def trigger_ome(self, name: str, *, timeout: float = 120.0, force: bool = False) -> dict:
        return await self._request(
            "POST",
            "/api/v1/ome/trigger",
            json={"name": name, "timeout": timeout, "force": force},
        )

    @staticmethod
    def _build_time_filters(start_time: str | None, end_time: str | None) -> dict | None:
        timestamp_filter: dict[str, str] = {}
        if start_time:
            timestamp_filter["gte"] = start_time
        if end_time:
            timestamp_filter["lte"] = end_time
        if not timestamp_filter:
            return None
        return {"timestamp": timestamp_filter}

    @staticmethod
    def _items_for_type(data: dict, memory_type: str) -> list[dict]:
        key = {
            "episode": "episodes",
            "profile": "profiles",
            "agent_case": "agent_cases",
            "agent_skill": "agent_skills",
        }.get(memory_type, "episodes")
        items = data.get(key, [])
        return items if isinstance(items, list) else []

    def _map_item(
        self,
        item: dict,
        *,
        memory_type: str | None = None,
        app_id: str | None = None,
        project_id: str | None = None,
    ) -> dict:
        mapped = dict(item)
        item_app = str(mapped.get("app_id") or app_id or "default")
        item_project = str(mapped.get("project_id") or project_id or "default")
        mapped["group_id"] = self._group_from_scope(item_app, item_project)
        if memory_type is not None:
            mapped["memory_type"] = memory_type
        elif "episode" in mapped:
            mapped["memory_type"] = "episodic_memory"
        elif "profile_data" in mapped:
            mapped["memory_type"] = "profile"
        elif "task_intent" in mapped:
            mapped["memory_type"] = "agent_case"
        elif "confidence" in mapped and "source_case_ids" in mapped:
            mapped["memory_type"] = "agent_skill"
        if "content" not in mapped:
            mapped["content"] = (
                mapped.get("summary")
                or mapped.get("episode")
                or mapped.get("description")
                or mapped.get("task_intent")
                or mapped.get("key_insight")
                or ""
            )
        return mapped

