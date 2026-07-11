from __future__ import annotations

import json
import hashlib
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
    create_minimal_vendored_codebase_fixture(fixture / "third_party" / "codebase-memory-mcp")
    create_minimal_basic_memory_fixture(fixture / "third_party" / "basic-memory")
    return fixture


def create_minimal_vendored_codebase_fixture(cbm: Path) -> None:
    cbm.mkdir(parents=True, exist_ok=True)
    (cbm / "src" / "mcp").mkdir(parents=True, exist_ok=True)
    internal = cbm / "internal" / "cbm"
    grammars = internal / "vendored" / "grammars"
    lsp = internal / "lsp"
    zlib = cbm / "vendored" / "zlib"
    grammars.mkdir(parents=True, exist_ok=True)
    lsp.mkdir(parents=True, exist_ok=True)
    zlib.mkdir(parents=True, exist_ok=True)
    (cbm / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (cbm / "THIRD_PARTY.md").write_text("third-party notices\n", encoding="utf-8")
    (cbm / "README.md").write_text("fixture vendored codebase-memory-mcp\n", encoding="utf-8")
    (cbm / "Makefile.cbm").write_text("cbm:\n\t@echo fixture\n", encoding="utf-8")
    (cbm / "src" / "mcp" / "mcp.c").write_text("/* fixture */\n", encoding="utf-8")
    (internal / "lsp_all.c").write_text("/* fixture */\n", encoding="utf-8")
    (zlib / "LICENSE").write_text("zlib license\n", encoding="utf-8")
    (zlib / "zlib.h").write_text("/* fixture */\n", encoding="utf-8")
    (zlib / "inflate.c").write_text("/* fixture */\n", encoding="utf-8")
    (grammars / "MANIFEST.md").write_text("Grammars: 159\n", encoding="utf-8")
    for index in range(159):
        (grammars / f"lang_{index:03d}").mkdir()
    lean = grammars / "lean"
    lean.mkdir(exist_ok=True)
    chunks = lean / "parser.c.chunks"
    chunks.mkdir()
    content = b"fixture lean parser\n"
    (chunks / "parser.c.part000").write_bytes(content)
    (chunks / "parser.c.sha256").write_text(f"{hashlib.sha256(content).hexdigest()}  parser.c\n", encoding="ascii")
    (chunks / "parser.c.size").write_text(str(len(content)), encoding="ascii")
    for name in [
        "py_lsp.c",
        "ts_lsp.c",
        "php_lsp.c",
        "cs_lsp.c",
        "go_lsp.c",
        "c_lsp.c",
        "java_lsp.c",
        "kotlin_lsp.c",
        "rust_lsp.c",
    ]:
        (lsp / name).write_text("/* fixture */\n", encoding="utf-8")


def create_minimal_basic_memory_fixture(bm: Path) -> None:
    (bm / "src" / "basic_memory" / "mcp").mkdir(parents=True, exist_ok=True)
    (bm / "src" / "basic_memory" / "markdown").mkdir(parents=True, exist_ok=True)
    (bm / "LICENSE").write_text(
        "                    GNU AFFERO GENERAL PUBLIC LICENSE\n",
        encoding="utf-8",
    )
    (bm / "pyproject.toml").write_text(
        "[project]\nname = \"basic-memory\"\nlicense = { text = \"AGPL-3.0-or-later\" }\n",
        encoding="utf-8",
    )
    (bm / "src" / "basic_memory" / "mcp" / "__init__.py").write_text("", encoding="utf-8")
    (bm / "src" / "basic_memory" / "markdown" / "entity_parser.py").write_text(
        "def parse_entities(text):\n    return []\n",
        encoding="utf-8",
    )


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


def test_platform_ci_covers_supported_os_and_architectures() -> None:
    workflow = (ROOT / ".github" / "workflows" / "platform-matrix.yml").read_text(
        encoding="utf-8"
    )
    for runner in [
        "ubuntu-24.04",
        "ubuntu-24.04-arm",
        "macos-15-intel",
        "macos-15",
        "windows-2025",
    ]:
        assert runner in workflow
    assert "windows-11-arm" not in workflow
    assert workflow.count("platform:") == 5
    for marker in [
        "lfs: true",
        "actions/checkout@v7.0.0",
        "actions/setup-python@v6.3.0",
        "astral-sh/setup-uv@v8.3.2",
        'python-version: "3.12"',
        "architecture: ${{ matrix.python_arch }}",
        "python_arch: arm64",
        "python_arch: x64",
        "uv sync --frozen",
        "test_release_consistency.py",
        "test_package_source_bundle.py",
    ]:
        assert marker in workflow


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


def test_runtime_release_wrappers_build_engine_and_call_shared_orchestrator() -> None:
    windows = (ROOT / "scripts" / "release-runtime.ps1").read_text(encoding="utf-8")
    unix = (ROOT / "scripts" / "release-runtime.sh").read_text(encoding="utf-8")

    for marker in [
        "build-vendored-codebase.ps1",
        "scripts.release_runtime_bundle",
        "dist\\runtime",
        "--codebase-binary",
        "--output-directory",
    ]:
        assert marker in windows
    for marker in [
        "build-vendored-codebase.sh",
        "scripts.release_runtime_bundle",
        "dist/runtime",
        "--codebase-binary",
        "--output-directory",
    ]:
        assert marker in unix
    assert "--target" in windows
    assert "--target" in unix


def test_unix_runtime_release_project_root_controls_default_output(
    tmp_path: Path,
) -> None:
    bash = shutil.which("bash")
    if platform.system() == "Windows":
        git_exec = run(["git", "--exec-path"]).stdout.strip()
        candidate = Path(git_exec).resolve().parents[2] / "usr" / "bin" / "bash.exe"
        bash = str(candidate) if candidate.is_file() else None
    if not bash:
        return

    project_root = tmp_path / "project"
    binary = tmp_path / "codebase-memory-mcp"
    fake_bin = tmp_path / "bin"
    captured = tmp_path / "uv-args.txt"
    project_root.mkdir()
    fake_bin.mkdir()
    binary.write_bytes(b"binary")
    uv = fake_bin / "uv"
    uv.write_text(
        "#!/usr/bin/env sh\nprintf '%s\\n' \"$@\" > \"$CAPTURED_ARGS\"\n",
        encoding="utf-8",
    )
    uv.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    env["CAPTURED_ARGS"] = str(captured)
    subprocess.run(
        [
            bash,
            str(ROOT / "scripts" / "release-runtime.sh"),
            "--project-root",
            str(project_root),
            "--codebase-binary",
            str(binary),
            "--target",
            "linux-x86_64",
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )

    args = captured.read_text(encoding="utf-8").splitlines()
    output_index = args.index("--output-directory") + 1
    assert Path(args[output_index]) == project_root / "dist" / "runtime"


def test_quick_start_scripts_use_builtin_engines_by_default() -> None:
    windows = (ROOT / "scripts" / "setup-windows.ps1").read_text(encoding="utf-8")
    macos = (ROOT / "scripts" / "setup-macos.sh").read_text(encoding="utf-8")

    assert "install-all.ps1" in windows
    assert "Built-in engines configured" in windows
    assert "install-all.sh" in macos
    assert "Built-in engines configured" in macos


def test_quick_start_scripts_require_python_312() -> None:
    windows = (ROOT / "scripts" / "setup-windows.ps1").read_text(encoding="utf-8")
    macos = (ROOT / "scripts" / "setup-macos.sh").read_text(encoding="utf-8")

    assert "$minor -ge 12" in windows
    assert '"$ver" -ge 312' in macos
    assert "Python 3.12+" in windows
    assert "Python 3.12+" in macos
    assert "Python 3.11" not in windows
    assert "Python 3.11" not in macos


def test_windows_setup_script_has_valid_powershell_syntax() -> None:
    if platform.system() != "Windows":
        return

    script = ROOT / "scripts" / "setup-windows.ps1"
    command = (
        "$tokens=$null; $errors=$null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{script}', "
        "[ref]$tokens, [ref]$errors); if($errors.Count){exit 1}"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        check=True,
    )


def test_install_all_scripts_do_not_install_external_engines_by_default() -> None:
    windows = (ROOT / "scripts" / "windows" / "install-all.ps1").read_text(encoding="utf-8")
    macos = (ROOT / "scripts" / "macos" / "install-all.sh").read_text(encoding="utf-8")

    forbidden = [
        "InstallExternalEngines",
        "INSTALL_EXTERNAL_ENGINES",
        "basic-memory==",
        "github.com/DeusData/codebase-memory-mcp",
        "EVERMIND_CODEBASE_MEMORY_PATH",
    ]
    for marker in forbidden:
        assert marker not in windows
        assert marker not in macos
    assert "Using EverMind built-in local archive and code graph engines" in windows
    assert "Using EverMind built-in local archive and code graph engines" in macos
    assert "install-toolchain.ps1" in windows
    assert "install-toolchain.sh" in macos
    assert "build-vendored-codebase.ps1" in windows
    assert "build-vendored-codebase.sh" in macos


def test_install_scripts_install_source_fusion_toolchains() -> None:
    windows = (ROOT / "scripts" / "windows" / "install-toolchain.ps1").read_text(encoding="utf-8")
    macos = (ROOT / "scripts" / "macos" / "install-toolchain.sh").read_text(encoding="utf-8")

    for marker in [
        "BrechtSanders.WinLibs.POSIX.UCRT",
        "Git.Git",
        "LLVM.LLVM",
        "ezwinports.make",
        "Kitware.CMake",
        "Ninja-build.Ninja",
    ]:
        assert marker in windows
    for marker in ["gcc", "g++", "sh", "mkdir", "rm"]:
        assert marker in windows
    for marker in ["xcode-select --install", "brew install", "llvm", "make", "cmake", "ninja"]:
        assert marker in macos


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
        "EVERMIND_EMBED_MODEL=Qwen/Qwen3-Embedding-8B",
        "EVERMIND_RERANK_MODEL=Qwen/Qwen3-Reranker-8B",
        "EVERMIND_LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash",
    ]:
        assert key in text
    assert "EVERMIND_CODEBASE_MEMORY_PATH" not in text
    assert "EVERMIND_BASIC_MEMORY_PATH" not in text


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
        "built-in local code graph",
        "built-in local Markdown archive",
        "archive_engine.py",
        "codebase_engine.py",
        "provider_boundary.py",
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
        "built-in local code graph",
        "built-in local archive",
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
            "-SkipToolchainInstall",
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
            "-SkipToolchainInstall",
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


def test_external_engine_cli_connectivity_is_not_required() -> None:
    windows_check = (ROOT / "scripts" / "windows" / "check-all.ps1").read_text(encoding="utf-8")
    macos_check = (ROOT / "scripts" / "macos" / "check-all.sh").read_text(encoding="utf-8")

    assert "Built-in EverMind Archive engine available" in windows_check
    assert "Built-in EverMind Code Graph engine available" in windows_check
    assert "Vendored codebase-memory-mcp source integrated" in windows_check
    assert "Built-in EverMind Archive engine available" in macos_check
    assert "Built-in EverMind Code Graph engine available" in macos_check
    assert "Vendored codebase-memory-mcp source integrated" in macos_check


def test_basic_memory_source_is_integrated_with_copyleft_boundary() -> None:
    bm = ROOT / "third_party" / "basic-memory"
    assert (bm / "LICENSE").read_text(encoding="utf-8").startswith(
        "                    GNU AFFERO GENERAL PUBLIC LICENSE"
    )
    assert "AGPL-3.0-or-later" in (bm / "pyproject.toml").read_text(encoding="utf-8")
    assert (bm / "src" / "basic_memory" / "mcp").is_dir()
    assert (bm / "src" / "basic_memory" / "markdown" / "entity_parser.py").exists()
    assert not (bm / ".git").exists()
    notice = (ROOT / "third_party" / "README.md").read_text(encoding="utf-8")
    assert "basic-memory" in notice
    assert "AGPL-3.0-or-later" in notice


def test_vendored_codebase_memory_source_is_integrated() -> None:
    cbm = ROOT / "third_party" / "codebase-memory-mcp"
    assert (cbm / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    assert (cbm / "Makefile.cbm").exists()
    assert (cbm / "src" / "mcp" / "mcp.c").exists()
    assert (cbm / "internal" / "cbm" / "lsp_all.c").exists()
    lsp = cbm / "internal" / "cbm" / "lsp"
    grammars = cbm / "internal" / "cbm" / "vendored" / "grammars"
    for name in [
        "py_lsp.c",
        "ts_lsp.c",
        "php_lsp.c",
        "cs_lsp.c",
        "go_lsp.c",
        "c_lsp.c",
        "java_lsp.c",
        "kotlin_lsp.c",
        "rust_lsp.c",
    ]:
        assert (lsp / name).exists()
    assert (grammars / "MANIFEST.md").exists()
    assert len([path for path in grammars.iterdir() if path.is_dir()]) >= 159
    chunks = grammars / "lean" / "parser.c.chunks"
    assert (chunks / "parser.c.sha256").exists()
    assert sorted(path.name for path in chunks.glob("parser.c.part*")) == [
        "parser.c.part000",
        "parser.c.part001",
        "parser.c.part002",
    ]
    zlib = cbm / "vendored" / "zlib"
    assert (zlib / "LICENSE").exists()
    assert (zlib / "zlib.h").exists()
    assert (zlib / "inflate.c").exists()
    makefile = (cbm / "Makefile.cbm").read_text(encoding="utf-8")
    assert "-Ivendored/zlib" in makefile
    assert "-lz" not in makefile


def test_vendored_source_has_no_plain_git_files_over_github_limit() -> None:
    restored_lean_parser = ROOT / "third_party" / "codebase-memory-mcp" / "internal" / "cbm" / "vendored" / "grammars" / "lean" / "parser.c"
    oversized = [
        path
        for path in (ROOT / "third_party" / "codebase-memory-mcp").rglob("*")
        if path.is_file()
        and path.stat().st_size >= 100_000_000
        and path != restored_lean_parser
        and "parser.c.chunks" not in path.parts
        and "build" not in path.parts
    ]
    assert "third_party/codebase-memory-mcp/internal/cbm/vendored/grammars/lean/parser.c" in (
        ROOT / ".gitignore"
    ).read_text(encoding="utf-8")
    assert oversized == []


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
            "-SkipToolchainInstall",
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


def test_mcp_interface_pytest_suite_passes() -> None:
    result = run(
        ["uv", "run", "--python", "3.12", "pytest", "-q"],
        cwd=ROOT / "mcp",
        timeout=300,
    )
    assert "passed" in result.stdout


