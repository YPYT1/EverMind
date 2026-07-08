<div align="center">

<img src="./png/everymind.png" alt="EverMind" width="420" />

**本地優先的六層 AI 記憶系統，專為程式設計師設計。**  
零配置。零雲端依賴。直接接入 Claude Code、Cursor、Codex。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?style=flat-square)](#架構)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](scripts/setup-windows.ps1)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](scripts/setup-macos.sh)

[快速開始](#快速開始) · [架構](#架構) · [MCP 工具](#mcp-工具) · [安裝](#安裝) · [文件](docs/README.md) · [English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

</div>

---

## EverMind 是什麼？

EverMind 為 AI 編程助手提供跨會話的持久記憶。它透過 MCP 直接嵌入 Claude Code、Cursor 和 Codex — 無需雲端服務，無需獨立程序，無需 API Key，只需指向你的倉庫即可使用。

記憶按照人類儲存知識的方式組織為六層：自動過期的工作筆記、情節事件、語義事實、流程知識、永久歸檔決策，以及實體關係圖譜。系統根據內容和重要性自動選擇合適的層級。

## 行業問題

AI 助手在每次會話之間會遺忘一切：

- 某個模組為什麼要這樣設計
- 哪條命令真正能建置或測試專案
- 已知的 bug 及有效的修復方法
- 部署流程和注意事項
- 個人偏好和編碼規範

EverMind 為 AI 助手提供一個可靠的地方來儲存和檢索這些知識。

## 架構

```text
          Claude Code / Cursor / Codex
                     |
                  MCP (stdio)
                     |
           +-----------------------+
           |   EverMind v2 核心    |
           |                       |
           |  remember / recall    |
           |  forget  / briefing   |
           +-----------+-----------+
                       |
           +-----------v-----------+
           |   SQLite              |
           |  (每個專案一個檔案)   |
           |                       |
           |  第1層: 工作記憶      |  24小時自動過期
           |  第2層: 情節記憶      |  事件和發現
           |  第3層: 語義記憶      |  專案事實
           |  第4層: 流程記憶      |  操作知識
           |  第5層: 歸檔記憶      |  永久決策
           |  第6層: 圖譜記憶      |  實體關係
           |                       |
           |  FTS5 關鍵詞搜尋      |
           |  sqlite-vec 向量搜尋  |
           |  事件日誌             |
           +-----------------------+
```

儲存路徑：`~/.evermind/<project-slug>.db` — 每個專案一個 SQLite 檔案，從 git remote 自動推斷專案名稱。

## 快速開始

### 1. 克隆倉庫

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
```

### 2. 執行安裝腳本

**Windows：**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

**macOS / Linux：**

```bash
bash scripts/setup-macos.sh
```

腳本會檢查 Python 3.11+，在缺少時安裝 uv，同步依賴，並自動配置 Claude Desktop 和 Cursor。

### 3. 手動配置（選用）

在 `claude_desktop_config.json` 中新增：

```json
{
  "mcpServers": {
    "evermind": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/EverMind/mcp", "evermind-mcp"]
    }
  }
}
```

將 `/path/to/EverMind` 替換為實際的克隆路徑，這是唯一需要修改的地方。

### 4. 啟用向量搜尋（選用，推薦）

```bash
cd mcp
uv pip install sqlite-vec sentence-transformers
```

不安裝也可以使用 FTS5 關鍵詞搜尋。安裝後，`recall()` 使用 BM25 + 向量 KNN 混合搜尋，語義查詢效果顯著更好。

## MCP 工具

| 工具 | 說明 |
|------|------|
| `remember(content, importance, tags)` | 儲存記憶。importance: 0=工作(24h), 1=長期, 2=永久 |
| `recall(query, limit, mode)` | 混合搜尋：BM25+語義，自動從 git 檢測專案空間 |
| `forget(id)` | 按 ID 刪除記憶 |
| `briefing()` | 載入會話上下文：當前專案的最近和重要記憶 |

記憶類型從內容自動檢測：bug 修復→情節記憶，架構決策→語義記憶，部署步驟→流程記憶。對於永遠不想被刪除的內容，設定 `importance=2`。

## 安裝

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

腳本功能：
- 檢查 Python 3.11+、uv、git
- 如未找到 uv，提供自動安裝選項
- 在 mcp 目錄執行 `uv sync`
- 自動更新 Claude Desktop 和 Cursor 的 MCP 配置
- 建立 `~/.evermind` 記憶目錄

### macOS

```bash
bash scripts/setup-macos.sh
```

與 Windows 步驟相同，使用 macOS 配置路徑（`~/Library/Application Support/Claude/`）。

### 手動安裝

```bash
# 安裝依賴
uv sync --directory mcp

# 選用：啟用向量搜尋（推薦）
cd mcp && uv pip install sqlite-vec sentence-transformers
```

## 記憶生命週期

| 層級 | 保留時間 | 用途 |
|------|---------|------|
| 工作記憶 | 24 小時 | 臨時筆記、進行中的上下文 |
| 情節記憶 | 長期 | 事件、bug 修復、發現 |
| 語義記憶 | 長期 | 專案相關事實 |
| 流程記憶 | 長期 | 部署步驟、工作流、操作指南 |
| 歸檔記憶 | 永久 | 架構決策、永久規則 |
| 圖譜記憶 | 永久 | 實體關係（Phase 3） |

- `importance=0` — 工作層（預設，24小時後過期）
- `importance=1` — 長期層（根據內容類型自動分類）
- `importance=2` — 歸檔層（永不刪除）

## Agent 指令

在 `CLAUDE.md` 或 `AGENTS.md` 中新增：

```markdown
## EverMind Memory

Call briefing() at session start to restore project context.
Call remember(content) for anything worth keeping across sessions.
Call recall(query) before starting work on a feature or bug.

importance=0: temporary working note (default)
importance=1: long-term memory
importance=2: permanent archive (architecture decisions, critical bugs)
```

## 文件

- [架構設計](docs/architecture.md)
- [MCP 工具參考](docs/mcp-tools.md)
- [配置說明](docs/configuration.md)
- [Windows 快速開始](docs/quickstart-windows.md)
- [macOS 快速開始](docs/quickstart-macos.md)
- [故障排除](docs/troubleshooting.md)
- [v2 重設計方案](docs/v2-redesign.md)

---

## 社區與支持

<div align="center">

<img src="./png/EverMind3群.png" width="200" /><br/>
<sub>EverMind 社群</sub>

</div>

<div align="center">

<img src="./png/wecha.png" width="200" /><br/>
<sub>微信</sub>

</div>

<div align="center">

<img src="./png/Alipay.jpg" width="200" /><br/>
<sub>支持作者 ☕</sub>

</div>

<div align="center">
為希望 AI 工具真正記住事情的工程師而建構。
</div>
