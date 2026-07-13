"""Provider boundary for EverMind local-first source-fused engines."""
from __future__ import annotations


def local_provider_boundary() -> dict:
    """Return the current product boundary for runtime providers."""
    return {
        "mode": "local",
        "sync_mode": "off",
        "cloud_enabled": False,
        "bridge_runtime_allowed": False,
        "code_graph_provider": "source-fused",
        "archive_provider": "source-fused",
    }
