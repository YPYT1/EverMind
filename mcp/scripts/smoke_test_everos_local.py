"""End-to-end smoke test for the local EverOS backend on port 3378."""

# ruff: noqa: E402

import asyncio
from uuid import uuid4

from common import add_project_src_to_path, pp

add_project_src_to_path()

from evermemos_mcp.everos_client import EverOSClient
from evermemos_mcp.memory_service import MemoryService
from evermemos_mcp.space_catalog_service import SpaceCatalogService


async def main() -> int:
    async with EverOSClient(base_url="http://127.0.0.1:3378") as client:
        health = await client.health()
        pp("health", health, max_len=800)

        catalog = SpaceCatalogService(client)
        svc = MemoryService(client, catalog)

        tag = uuid4().hex[:8]
        coding_space = f"coding:smoke-{tag}"
        chat_space = f"chat:smoke-{tag}"

        remembered = await svc.remember(
            coding_space,
            f"Local EverOS smoke fact {tag}: coord-picker uses a 3378 memory backend.",
            description="Local EverOS smoke test",
            flush=False,
            include_status=False,
        )
        pp("remember", remembered, max_len=1200)
        assert remembered["ok"] is True

        recalled = await svc.recall(
            f"3378 memory backend {tag}",
            space_id=coding_space,
            retrieve_method="keyword",
            top_k=5,
        )
        pp("recall", recalled, max_len=1600)
        assert recalled["ok"] is True

        history = await svc.fetch_history(coding_space, limit=5)
        pp("fetch_history", history, max_len=1600)
        assert history["ok"] is True

        briefing = await svc.briefing(coding_space, max_items=5)
        pp("briefing", briefing, max_len=1600)
        assert briefing["ok"] is True
        assert "basic_memory" in briefing

        await svc.remember(
            chat_space,
            f"Local EverOS smoke isolation fact {tag}: this belongs to chat only.",
            flush=False,
        )
        isolated = await svc.recall(
            f"chat only {tag}",
            space_id=coding_space,
            retrieve_method="keyword",
            top_k=5,
        )
        pp("space_isolation_check", isolated, max_len=1200)
        assert isolated["ok"] is True

    print("\n=== Local EverOS smoke test complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
