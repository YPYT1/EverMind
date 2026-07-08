"""Tests for config env parsing."""

from __future__ import annotations

import importlib
from unittest.mock import patch

from evermind_mcp import config as config_module


def _reload_config_module():
    return importlib.reload(config_module)


def test_source_recovery_probe_env_overrides(monkeypatch):
    monkeypatch.setenv("EVERMIND_MCP_BACKEND", "cloud")
    monkeypatch.setenv("EVERMIND_MCP_SOURCE_RECOVERY_PROBE_TOP_K", "55")
    monkeypatch.setenv("EVERMIND_MCP_SOURCE_RECOVERY_PROBE_CONCURRENCY", "6")

    reloaded = _reload_config_module()
    assert reloaded.EVERMIND_MCP_SOURCE_RECOVERY_PROBE_TOP_K == 55
    assert reloaded.EVERMIND_MCP_SOURCE_RECOVERY_PROBE_CONCURRENCY == 6

    monkeypatch.delenv("EVERMIND_MCP_SOURCE_RECOVERY_PROBE_TOP_K", raising=False)
    monkeypatch.delenv("EVERMIND_MCP_SOURCE_RECOVERY_PROBE_CONCURRENCY", raising=False)
    _reload_config_module()


def test_source_recovery_probe_env_clamps_invalid_values(monkeypatch):
    monkeypatch.setenv("EVERMIND_MCP_BACKEND", "cloud")
    monkeypatch.setenv("EVERMIND_MCP_SOURCE_RECOVERY_PROBE_TOP_K", "-3")
    monkeypatch.setenv("EVERMIND_MCP_SOURCE_RECOVERY_PROBE_CONCURRENCY", "99")

    reloaded = _reload_config_module()
    assert reloaded.EVERMIND_MCP_SOURCE_RECOVERY_PROBE_TOP_K == 1
    assert reloaded.EVERMIND_MCP_SOURCE_RECOVERY_PROBE_CONCURRENCY == 10

    monkeypatch.delenv("EVERMIND_MCP_SOURCE_RECOVERY_PROBE_TOP_K", raising=False)
    monkeypatch.delenv("EVERMIND_MCP_SOURCE_RECOVERY_PROBE_CONCURRENCY", raising=False)
    _reload_config_module()


# -- git repo auto-detection --


def test_detect_git_repo_name_github_ssh():
    import subprocess

    def mock_run(*args, **kwargs):
        result = subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="git@github.com:user/my-app.git\n",
            stderr="",
        )
        return result

    with patch("evermind_mcp.config.subprocess.run", side_effect=mock_run):
        assert config_module._detect_git_repo_name() == "my-app"


def test_detect_git_repo_name_github_https():
    import subprocess

    def mock_run(*args, **kwargs):
        result = subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="https://github.com/user/my-app.git\n",
            stderr="",
        )
        return result

    with patch("evermind_mcp.config.subprocess.run", side_effect=mock_run):
        assert config_module._detect_git_repo_name() == "my-app"


def test_detect_git_repo_name_no_git():
    with patch(
        "evermind_mcp.config.subprocess.run",
        side_effect=FileNotFoundError,
    ):
        assert config_module._detect_git_repo_name() is None


def test_detect_git_repo_name_not_a_repo():
    import subprocess

    def mock_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0], returncode=128, stdout="", stderr="fatal: not a git repo"
        )

    with patch("evermind_mcp.config.subprocess.run", side_effect=mock_run):
        assert config_module._detect_git_repo_name() is None


def test_resolve_default_space_env_override(monkeypatch):
    monkeypatch.setenv("EVERMIND_MCP_BACKEND", "cloud")
    monkeypatch.setenv("EVERMIND_MCP_DEFAULT_SPACE", "study:ml")
    reloaded = _reload_config_module()
    assert reloaded.EVERMIND_MCP_DEFAULT_SPACE == "study:ml"
    monkeypatch.delenv("EVERMIND_MCP_DEFAULT_SPACE", raising=False)
    _reload_config_module()


def test_local_everos_backend_is_default(monkeypatch):
    monkeypatch.delenv("EVERMIND_MCP_BACKEND", raising=False)
    reloaded = _reload_config_module()
    assert reloaded.EVERMIND_MCP_BACKEND == "everos"


