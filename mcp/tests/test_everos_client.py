"""Tests for the local EverOS adapter."""
# ruff: noqa: E402

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytest.skip("Legacy EverOS client tests are not part of MCP v2.", allow_module_level=True)

from evermind_mcp.everos_client import EverOSClient


@pytest.mark.asyncio
async def test_add_message_maps_agent_space_to_agent_sender_and_flushes():
    client = EverOSClient(base_url="http://127.0.0.1:3378")
    client._request = AsyncMock(
        side_effect=[
            {"request_id": "add-1", "data": {"status": "accumulated"}},
            {"request_id": "flush-1", "data": {"status": "extracted"}},
        ]
    )

    result = await client.add_message(
        "space::agent:codex",
        "Codex fixed the local memory adapter.",
        role="user",
        flush=True,
        message_id="session-1",
    )

    assert result["status"] == "completed"
    assert result["message_id"] == "session-1"

    add_call = client._request.call_args_list[0]
    assert add_call.args == ("POST", "/api/v1/memory/add")
    add_payload = add_call.kwargs["json"]
    assert add_payload["app_id"] == "agent"
    assert add_payload["project_id"] == "codex"
    assert add_payload["messages"][0]["sender_id"] == "codex"
    assert add_payload["messages"][0]["role"] == "assistant"

    flush_call = client._request.call_args_list[1]
    assert flush_call.args == ("POST", "/api/v1/memory/flush")
    assert flush_call.kwargs["json"]["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_fetch_memories_maps_agent_case_to_agent_id():
    client = EverOSClient(base_url="http://127.0.0.1:3378")
    client._request = AsyncMock(
        return_value={
            "data": {
                "agent_cases": [
                    {
                        "id": "case-1",
                        "agent_id": "codex",
                        "task_intent": "Fix memory integration",
                    }
                ],
                "count": 1,
                "total_count": 1,
            }
        }
    )

    result = await client.fetch_memories(
        "space::agent:codex",
        memory_type="agent_case",
        limit=10,
    )

    _, kwargs = client._request.call_args
    payload = kwargs["json"]
    assert payload["agent_id"] == "codex"
    assert "user_id" not in payload
    assert payload["memory_type"] == "agent_case"
    assert result["result"]["memories"][0]["group_id"] == "space::agent:codex"
    assert result["result"]["memories"][0]["memory_type"] == "agent_case"


@pytest.mark.asyncio
async def test_search_agent_space_returns_agent_memories():
    client = EverOSClient(base_url="http://127.0.0.1:3378")
    client._request = AsyncMock(
        return_value={
            "data": {
                "episodes": [],
                "profiles": [],
                "agent_cases": [
                    {
                        "id": "case-1",
                        "agent_id": "codex",
                        "task_intent": "Investigate failing tests",
                        "score": 0.8,
                    }
                ],
                "agent_skills": [],
            }
        }
    )

    result = await client.search_memories(
        "failing tests",
        "space::agent:codex",
        memory_types=["agent_case", "agent_skill"],
    )

    _, kwargs = client._request.call_args
    payload = kwargs["json"]
    assert payload["agent_id"] == "codex"
    assert "user_id" not in payload
    assert payload["include_profile"] is False
    memories = result["result"]["memories"]
    assert memories[0]["memory_type"] == "agent_case"
    assert memories[0]["content"] == "Investigate failing tests"

