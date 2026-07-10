from __future__ import annotations

from pathlib import Path

from evermind_mcp.config_v2 import EverMindConfig
import evermind_mcp.vendored_codebase as vendored_codebase


def test_verified_official_codebase_binary_runs_without_source_tree(
    tmp_path: Path, monkeypatch
) -> None:
    bundle_root = tmp_path / "EverMind"
    binary = bundle_root / "bin" / "codebase-memory-mcp.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"verified binary")
    missing_source = bundle_root / "sources" / "codebase-memory-mcp"
    monkeypatch.setattr(
        vendored_codebase, "find_official_bundle_root", lambda: bundle_root
    )
    monkeypatch.setattr(
        vendored_codebase,
        "is_official_bundle_verified",
        lambda bundle_root=None: True,
        raising=False,
    )
    captured = {}

    def run(_command, **kwargs):
        captured["cwd"] = kwargs["cwd"]
        return type(
            "Completed",
            (),
            {"returncode": 0, "stdout": '{"ok": true}', "stderr": ""},
        )()

    monkeypatch.setattr(vendored_codebase.subprocess, "run", run)
    backend = vendored_codebase.VendoredCodebase(
        EverMindConfig(
            home=tmp_path / "home",
            codebase_source_dir=missing_source,
            codebase_binary_path=binary,
            embed_enabled=False,
            embed_warmup_on_start=False,
        )
    )

    metadata = backend.metadata()
    result = backend.call("search_code", {"pattern": "MemoryService"})

    assert backend.source_available is False
    assert backend.available is True
    assert metadata["source_integrated"] is True
    assert metadata["bundle_verified"] is True
    assert metadata["missing_source_files"] == []
    assert Path(captured["cwd"]) == binary.parent
    assert result["ok"] is True
