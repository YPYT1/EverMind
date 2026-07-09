from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(
    args: list[str],
    *,
    cwd: Path = ROOT,
    timeout: int = 60,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in [
        "PYTHONHOME",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "UV_PROJECT_ENVIRONMENT",
        "UV_PYTHON",
    ]:
        env.pop(key, None)
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=check,
    )


def copy_script_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "EverMind"
    for name in ["agents", "scripts", "skills", "templates", ".env.example"]:
        source = ROOT / name
        target = fixture / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (fixture / "mcp").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "mcp" / "pyproject.toml", fixture / "mcp" / "pyproject.toml")
    return fixture


def test_required_top_level_layout_exists() -> None:
    expected = [
        "README.md",
        "README.zh-CN.md",
        "README.zh-TW.md",
        "README.ja.md",
        "LICENSE",
        ".env.example",
        "agents",
        "config",
        "docs",
        "mcp",
        "scripts",
        "skills",
        "templates",
        "tests",
    ]
    missing = [item for item in expected if not (ROOT / item).exists()]
    assert missing == []


def test_required_mcp_bundle_assets_exist() -> None:
    mcp_root = ROOT / "mcp"
    expected = [
        "README.md",
        "README.zh-CN.md",
        "CHANGELOG.md",
        "notes.md",
        "notes.zh-CN.md",
        "pyproject.toml",
        "task_plan.md",
        "task_plan.zh-CN.md",
        "uv.lock",
        "src",
        "tests",
        "scripts",
        "docs",
    ]
    missing = [item for item in expected if not (mcp_root / item).exists()]
    assert missing == []


def test_required_user_setup_scripts_exist() -> None:
    expected = [
        "scripts/windows/bootstrap.ps1",
        "scripts/windows/install.ps1",
        "scripts/windows/install-all.ps1",
        "scripts/windows/check.ps1",
        "scripts/windows/check-all.ps1",
        "scripts/windows/configure.ps1",
        "scripts/windows/setup-user.ps1",
        "scripts/windows/start-mcp.ps1",
        "scripts/windows/start-everos.ps1",
        "scripts/windows/install-everos-nssm.ps1",
        "scripts/macos/bootstrap.sh",
        "scripts/macos/install.sh",
        "scripts/macos/install-all.sh",
        "scripts/macos/check.sh",
        "scripts/macos/check-all.sh",
        "scripts/macos/configure.sh",
        "scripts/macos/setup-user.sh",
        "scripts/macos/start-mcp.sh",
        "scripts/macos/start-everos.sh",
    ]
    missing = [item for item in expected if not (ROOT / item).exists()]
    assert missing == []


def test_quick_start_scripts_install_integrated_engines() -> None:
    windows = (ROOT / "scripts" / "setup-windows.ps1").read_text(encoding="utf-8")
    macos = (ROOT / "scripts" / "setup-macos.sh").read_text(encoding="utf-8")

    assert "install-all.ps1" in windows
    assert "Integrated engines installed" in windows
    assert "install-all.sh" in macos
    assert "Integrated engines installed" in macos


def test_json_and_toml_templates_parse() -> None:
    json_files = list((ROOT / "agents").rglob("*.json")) + list(
        (ROOT / "templates" / "mcp-config").glob("*.json")
    )
    toml_files = list((ROOT / "agents").rglob("*.toml")) + list(
        (ROOT / "templates" / "mcp-config").glob("*.toml")
    )

    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))
    for path in toml_files:
        tomllib.loads(path.read_text(encoding="utf-8"))


def test_no_standalone_third_party_notice_files() -> None:
    assert not (ROOT / "THIRD_PARTY_NOTICES.md").exists()
    assert not (ROOT / "third_party.lock.yaml").exists()


def test_env_example_contains_orchestration_and_cloud_reserved_fields() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in [
        "EVERMIND_HOME=",
        "EVERMIND_DEFAULT_SPACE=",
        "EVERMIND_ARCHIVE_ROOT=",
        "EVERMIND_ARCHIVE_CANDIDATE_DIR=",
        "EVERMIND_CODEBASE_MEMORY_PATH=",
        "EVERMIND_EMBED_MODEL=Qwen/Qwen3-Embedding-8B",
        "EVERMIND_RERANK_MODEL=Qwen/Qwen3-Reranker-8B",
        "EVERMIND_LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash",
    ]:
        assert key in text


def test_config_directory_has_one_unified_config_file() -> None:
    files = sorted(path.name for path in (ROOT / "config").iterdir() if path.is_file())
    assert "evermind.example.yaml" in files


def test_unified_config_defines_write_policy_and_router() -> None:
    config = (ROOT / "config" / "evermind.example.yaml").read_text(encoding="utf-8")
    for section in [
        "storage:",
        "embedding:",
        "reranker:",
        "llm_extraction:",
        "siliconflow:",
        "MCP Server",
        "evermind-mcp",
    ]:
        assert section in config


def test_docs_explain_integrated_components_and_cloud_roadmap() -> None:
    components = (ROOT / "docs" / "components.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "local-to-cloud-roadmap.md").read_text(
        encoding="utf-8"
    )
    architecture = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    for phrase in [
        "EverMind MCP",
        "Codebase Memory",
        "Basic Memory",
        "archive_bridge.py",
        "codebase_engine.py",
    ]:
        assert phrase in components
    assert "MCP Server" in architecture
    assert "Storage" in architecture
    assert "42 unified tools" in architecture
    assert "EVERMIND_MEMORY_MODE=local" in roadmap
    assert "EVERMIND_SYNC_MODE=off" in roadmap


def test_readme_explains_value_principles_and_folded_commands() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    zht = (ROOT / "README.zh-TW.md").read_text(encoding="utf-8")
    ja = (ROOT / "README.ja.md").read_text(encoding="utf-8")
    for phrase in [
        "persistent memory across sessions",
        "42 tools",
        "codebase-memory-mcp v0.9.0",
        "basic-memory v0.22.1",
        "update_memory",
        "Memory Lifecycle",
        "Built for engineers",
    ]:
        assert phrase in readme
    for phrase in [
        "跨会话的持久记忆",
        "42 个工具",
        "update_memory",
        "记忆生命周期",
        "社群",
    ]:
        assert phrase in zh
    for phrase in [
        "跨會話的持久記憶",
        "42 個工具",
        "update_memory",
        "社群",
    ]:
        assert phrase in zht
    for phrase in [
        "セッションを越えた永続的なメモリ",
        "42 個のツール",
        "update_memory",
        "コミュニティ",
    ]:
        assert phrase in ja


def test_no_personal_paths_in_public_templates() -> None:
    paths = [
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        ROOT / "README.zh-TW.md",
        ROOT / "README.ja.md",
        ROOT / "agents",
        ROOT / "config",
        ROOT / "docs",
        ROOT / "skills",
        ROOT / "templates",
    ]
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in paths
        for path in ([root] if root.is_file() else root.rglob("*"))
        if path.is_file()
    )
    forbidden = [
        r"C:\Users\Administrator",
        r"D:\EverOSMemory",
        r"D:\BasicMemory",
    ]
    for marker in forbidden:
        assert marker not in combined


def test_public_templates_do_not_reference_nested_mcp_directory() -> None:
    paths = [
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        ROOT / "README.zh-TW.md",
        ROOT / "README.ja.md",
        ROOT / "agents",
        ROOT / "docs",
        ROOT / "templates",
    ]
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in paths
        for path in ([root] if root.is_file() else root.rglob("*"))
        if path.is_file()
    )
    assert "mcp/evermind-mcp" not in combined
    assert r"mcp\evermind-mcp" not in combined


def test_render_configs_updates_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text((ROOT / ".env.example").read_text(encoding="utf-8"))
    result = run(
        [
            sys.executable,
            str(ROOT / "scripts" / "common" / "render-configs.py"),
            "--env-file",
            str(env_file),
            "--evermind-home",
            str(tmp_path / "home"),
            "--everos-root",
            str(tmp_path / "home" / "everos"),
            "--archive-root",
            str(tmp_path / "basic"),
            "--archive-candidate-dir",
            str(tmp_path / "basic" / ".candidates"),
        ]
    )
    assert result.returncode == 0
    rendered = env_file.read_text(encoding="utf-8")
    assert f"EVERMIND_HOME={tmp_path / 'home'}" in rendered
    assert f"EVEROS_ROOT={tmp_path / 'home' / 'everos'}" in rendered
    assert f"EVERMIND_ARCHIVE_ROOT={tmp_path / 'basic'}" in rendered
    assert f"EVERMIND_ARCHIVE_CANDIDATE_DIR={tmp_path / 'basic' / '.candidates'}" in rendered


def test_windows_install_all_skip_install_generates_local_config(tmp_path: Path) -> None:
    if platform.system() != "Windows":
        return

    project_root = copy_script_fixture(tmp_path)
    env_file = project_root / ".env"
    generated = project_root / "generated"

    result = run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "scripts" / "windows" / "install-all.ps1"),
            "-SkipToolInstall",
            "-ProjectRoot",
            str(project_root),
            "-EverMindHome",
            str(tmp_path / "EverMindMemory"),
        ],
        cwd=project_root,
        timeout=90,
    )
    assert result.returncode == 0
    assert "No client config files were overwritten" in result.stdout
    assert env_file.exists()
    assert (generated / "mcp-config" / "codex.toml").exists()
    rendered = (generated / "mcp-config" / "codex.toml").read_text(
        encoding="utf-8-sig"
    )
    assert "<EVERMIND_ROOT>" not in rendered
    assert "<EVEROS_ROOT>" not in rendered
    assert "<EVERMIND_ARCHIVE_ROOT>" not in rendered


def test_windows_configure_noninteractive_generates_user_assets(tmp_path: Path) -> None:
    if platform.system() != "Windows":
        return

    project_root = copy_script_fixture(tmp_path)
    env_file = project_root / ".env"
    generated = project_root / "generated"
    user_home = tmp_path / "user"

    result = run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "scripts" / "windows" / "configure.ps1"),
            "-NonInteractive",
            "-CopySkillsInsteadOfSymlink",
            "-ProjectRoot",
            str(project_root),
            "-UserHome",
            str(user_home),
            "-EverMindHome",
            str(tmp_path / "EverMindMemory"),
            "-LlmApiKey",
            "dummy-llm",
            "-EmbeddingApiKey",
            "dummy-embedding",
        ],
        cwd=project_root,
        timeout=90,
    )
    assert result.returncode == 0
    assert "Configuration complete" in result.stdout
    assert env_file.exists()
    env_text = env_file.read_text(encoding="utf-8")
    assert "EVEROS_LLM__API_KEY=dummy-llm" in env_text
    assert "EVEROS_EMBEDDING__API_KEY=dummy-embedding" in env_text
    assert (generated / "mcp-config" / "codex.toml").exists()
    assert (user_home / ".agents" / "skills" / "evermind" / "SKILL.md").exists()


def test_external_basic_memory_cli_connectivity() -> None:
    if not shutil.which("basic-memory"):
        raise AssertionError("basic-memory CLI is not installed or not on PATH")
    version = run(["basic-memory", "--version"], timeout=30).stdout
    assert "Basic Memory version" in version
    status = run(["basic-memory", "status"], timeout=60).stdout
    assert "Status" in status


def test_external_codebase_memory_cli_connectivity() -> None:
    if not shutil.which("codebase-memory-mcp"):
        raise AssertionError("codebase-memory-mcp CLI is not installed or not on PATH")
    version = run(["codebase-memory-mcp", "--version"], timeout=30).stdout
    assert "codebase-memory-mcp" in version
    projects = run(
        ["codebase-memory-mcp", "cli", "list_projects", "{}"], timeout=60
    ).stdout
    assert '"projects"' in projects


def test_windows_full_stack_check_connectivity_with_dummy_model_keys(tmp_path: Path) -> None:
    if platform.system() != "Windows":
        return

    project_root = copy_script_fixture(tmp_path)
    env_file = project_root / ".env"

    run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "scripts" / "windows" / "install-all.ps1"),
            "-SkipToolInstall",
            "-ProjectRoot",
            str(project_root),
            "-EverMindHome",
            str(tmp_path / "EverMindMemory"),
        ],
        cwd=project_root,
        timeout=90,
    )
    text = env_file.read_text(encoding="utf-8")
    for key in [
        "EVEROS_LLM__API_KEY",
        "EVEROS_MULTIMODAL__API_KEY",
        "EVEROS_EMBEDDING__API_KEY",
        "EVEROS_RERANK__API_KEY",
    ]:
        text = text.replace(f"# {key}=", f"{key}=dummy-local-check")
        text = text.replace(f"{key}=", f"{key}=dummy-local-check")
    env_file.write_text(text, encoding="utf-8")

    result = run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "scripts" / "windows" / "check-all.ps1"),
            "-ProjectRoot",
            str(project_root),
        ],
        cwd=project_root,
        timeout=90,
    )
    assert "EverMind full stack checks passed" in result.stdout


def test_mcp_bridge_pytest_suite_passes() -> None:
    result = run(
        ["uv", "run", "--python", "3.12", "pytest", "-q"],
        cwd=ROOT / "mcp",
        timeout=180,
    )
    assert "passed" in result.stdout


