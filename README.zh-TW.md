<div align="center">

# EverMind

**面向 AI 輔助軟體工程的本地優先上下文持久化系統。**

[![EverMind](https://img.shields.io/badge/EverMind-Context%20Persistence-2E86AB?style=flat-square)](https://github.com/YPYT1/EverMind)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](docs/quickstart-windows.md)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](docs/quickstart-macos.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)

[快速開始](#安裝與使用) · [系統架構](#系統架構) · [核心概念](#核心概念) · [整合方式](#整合方式) · [English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

</div>

## 一句話定義

EverMind 是一層面向 AI 輔助軟體工程的本地記憶基礎設施。

它讓專案上下文能跨會話持續存在，將快速工作記憶與經過審核的長期知識分離，並為 coding agents 提供恢復、檢索、演化和驗證專案知識的穩定入口。

EverMind 不是 Agent 框架，不是向量資料庫，也不是單獨的 RAG 應用。它更接近 AI 編碼系統下方的上下文持久化層。

## 問題背景

AI coding agents 通常受限於短生命週期上下文。即使它們能讀檔案、能呼叫工具，也會在會話之間遺失關鍵工程語境：

- 模組為什麼如此設計；
- 哪個命令能驗證某個行為；
- runtime data、索引與產物放在哪裡；
- 之前失敗過的實作細節是什麼；
- 哪些事實穩定到可以成為專案知識；
- 哪些內容只是臨時觀察，不應污染長期文件。

RAG 和向量搜尋能找文字，但它們沒有定義完整的知識生命週期。Agent 框架能調度行為，但通常不負責專案知識的長期可信沉澱。EverMind 補上的是這個基礎設施層。

## 核心解法

EverMind 把記憶建模為生命週期，而不是一次儲存操作。

```text
工作上下文 -> 可檢索記憶 -> 已審核知識 -> 可複用專案智能
```

這帶來三個能力：

- **連續性**：下一次會話可以從已知專案上下文開始。
- **結構性**：記憶依專案、agent、長期檔案和程式碼圖譜分層路由。
- **可信性**：長期知識進入正式檔案前需要候選與確認。

## 系統架構

```text
AI Coding Interfaces
  Codex / Claude Code / Cursor / Devin
  agent instructions and skills
  generated MCP configuration

EverMind Orchestration Layer
  setup and health checks
  EverMind MCP bridge
  memory routing
  write policy
  archive candidate flow
  code graph access

Local Knowledge Substrate
  realtime project memory
  reviewed Markdown archive
  repository graph index
  runtime configuration and local paths
```

EverMind 位於 AI coding agents 與本地知識儲存之間。不同 agent 可以共享相同記憶語義；策略層決定記憶如何被檢索、寫入、提案或忽略；本地知識層負責持久化。

## 核心概念

- **上下文持久化**：專案上下文不隨聊天視窗結束而消失。
- **記憶生命週期**：`briefing`、`recall`、`remember`、candidate、commit 對應不同可信等級。
- **已審核知識**：長期知識以 Markdown 保存，方便閱讀、diff、備份與遷移。
- **程式碼庫上下文**：記憶需要連接架構、呼叫鏈、片段與影響範圍。
- **本地優先**：預設把記憶與專案知識保留在使用者本機。

## 核心能力

| 能力 | 說明 |
| --- | --- |
| 會話恢復 | 透過 briefing 啟動任務，而不是每次冷啟動閱讀專案。 |
| 語義檢索 | 檢索專案事實、歷史決策、坑點與偏好。 |
| 工作記憶 | 在開發過程保存有價值的上下文。 |
| 審核式檔案 | 只有確認後的事實才進入正式 Markdown 知識庫。 |
| 程式碼圖譜理解 | 支援架構、呼叫鏈、程式碼搜尋、片段與影響分析。 |
| 多 agent 複用 | Codex、Claude Code、Cursor、Devin 可使用同一套記憶系統。 |

## 使用場景

- 隔幾天繼續開發功能，不必重新閱讀整個倉庫。
- 修改模組前，讓 agent 回憶之前的架構決策。
- 將測試命令、執行路徑和已知坑點沉澱成專案知識。
- 完成任務後產生帶證據的變更記憶候選。
- 修改共享函式前分析呼叫鏈和影響範圍。

## 安裝與使用

<details>
<summary><strong>Windows：互動式配置</strong></summary>

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\configure.ps1
```

</details>

<details>
<summary><strong>macOS：互動式配置</strong></summary>

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
bash scripts/macos/configure.sh
```

</details>

配置後複製對應工具的 MCP 設定：

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

## 整合方式

```text
Agent client
  -> generated MCP snippet
  -> uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
  -> EverMind MCP tools
  -> local memory, archive, and code graph layers
```

## 路線圖

- 改進非互動式安裝。
- 擴充大型倉庫的檔案模板。
- 增強 MCP 啟動失敗診斷。
- 維持本地優先作為預設模式。
- 預留可選雲同步，但不把雲記憶作為必要依賴。

## Community and Support

歡迎 issue 和 pull request。如果 EverMind 對你的本地 AI 記憶工作流有幫助，star、回饋或小額支持都能讓專案繼續向前。

<div align="center">
  <p><strong>EverMind 交流群</strong></p>
  <img src="png/EverMind3群.png" alt="EverMind 交流群二維碼" width="260">
</div>

<div align="center">
  <p><strong>支持專案</strong></p>
  <img src="png/Alipay.jpg" alt="支付寶支持二維碼" width="220">
  <img src="png/wecha.png" alt="微信支持二維碼" width="220">
</div>
