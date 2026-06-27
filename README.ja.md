<div align="center">

# EverMind

**AI 支援ソフトウェア開発のための、ローカルファーストなコンテキスト永続化システム。**

[![EverMind](https://img.shields.io/badge/EverMind-Context%20Persistence-2E86AB?style=flat-square)](https://github.com/YPYT1/EverMind)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](docs/quickstart-windows.md)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](docs/quickstart-macos.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)

[Quick Start](#インストールと利用) · [Architecture](#システムアーキテクチャ) · [Concepts](#中核概念) · [Integration](#統合モデル) · [English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

</div>

## 定義

EverMind は、AI 支援ソフトウェア開発のためのローカルファーストな記憶インフラストラクチャです。

プロジェクトのコンテキストをセッションを越えて保持し、高速な作業記憶とレビュー済みの長期知識を分離し、coding agent がプロジェクト知識を復元、検索、更新、検証するための安定した入口を提供します。

EverMind は Agent フレームワークでも、ベクトルデータベースでも、単体の RAG アプリケーションでもありません。AI 開発環境の下に置かれる、コンテキスト永続化レイヤーです。

## 背景

AI coding agents は通常、短命なコンテキストウィンドウに依存しています。ファイルを読めても、ツールを呼び出せても、セッションをまたぐと重要な開発文脈が失われます。

- なぜそのモジュールがその設計になったのか。
- どのコマンドで動作を検証できるのか。
- runtime data、インデックス、生成物がどこにあるのか。
- 以前失敗した実装上の注意点は何か。
- どの事実が長期的なプロジェクト知識として安定しているのか。
- どの情報は一時的で、長期ドキュメントに入れるべきではないのか。

RAG やベクトル検索はテキスト検索には有効ですが、知識のライフサイクルまでは定義しません。Agent フレームワークは行動を調整できますが、信頼できるプロジェクト知識の永続化を主目的にはしません。EverMind はこの間のレイヤーを担います。

## 中核となる解決策

EverMind は記憶を単なる保存処理ではなく、ライフサイクルとして扱います。

```text
working context -> searchable memory -> reviewed knowledge -> reusable project intelligence
```

このモデルにより、AI 開発システムは次の性質を持てます。

- **継続性**：次のセッションを既知のプロジェクト文脈から開始できる。
- **構造化**：記憶をプロジェクト、agent、アーカイブ、コードグラフの関心ごとに分けられる。
- **信頼性**：長期知識はレビュー後に正式な Markdown ノートになる。

## システムアーキテクチャ

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

EverMind は AI coding agents とローカル知識ストアの間に位置します。agent 側は置き換え可能で、オーケストレーション層がポリシーを持ち、ローカル知識基盤が永続化を担当します。

## 中核概念

### コンテキスト永続化

プロジェクトの文脈はチャットセッションとともに消えるべきではありません。EverMind は、過去の判断、実行規約、既知の問題、検証方法を agent が復元できるようにします。

### 記憶ライフサイクル

1. `briefing` で作業開始時に文脈を復元する。
2. `recall` で関連する過去の記憶を検索する。
3. `remember` で有用な作業事実を保存する。
4. `propose_basic_memory_update` でアーカイブ候補を作成する。
5. `commit_basic_memory_update` は明示的な確認後にのみ正式知識へ昇格する。

### レビュー済み知識

長期的なプロジェクト知識は、安定し、根拠があり、読める形式であるべきです。EverMind Archive はレビュー後の知識を Markdown として保存します。

### コードベース文脈

ソフトウェアの記憶は文章だけではありません。構造、呼び出し経路、コード断片、変更影響も必要です。EverMind は Code Graph により記憶を実際のリポジトリ構造に接続します。

## 中核機能

| 機能 | 内容 |
| --- | --- |
| セッション復元 | cold start ではなく briefing から作業を始める。 |
| 意味検索 | 事実、判断、既知の問題、設定を検索する。 |
| 作業記憶 | 開発中の有用な文脈を保存する。 |
| レビュー済みアーカイブ | 確認された知識だけを正式な Markdown にする。 |
| コードグラフ理解 | 構造、呼び出し経路、検索、断片、影響分析を扱う。 |
| 複数 agent 対応 | Codex、Claude Code、Cursor、Devin から同じ記憶層を使う。 |

## 利用シーン

- 数日後に機能開発を再開する。
- モジュール変更前に過去の設計判断を確認する。
- テストコマンド、runtime path、既知の問題をプロジェクト知識として残す。
- 作業完了後に根拠付きの記憶候補を作る。
- 共有関数の変更前に呼び出し経路と影響範囲を確認する。

## インストールと利用

<details>
<summary><strong>Windows: guided setup</strong></summary>

```powershell
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\configure.ps1
```

</details>

<details>
<summary><strong>macOS: guided setup</strong></summary>

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
bash scripts/macos/configure.sh
```

</details>

セットアップ後、利用するクライアントの MCP 設定をコピーします。

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

## 統合モデル

```text
Agent client
  -> generated MCP snippet
  -> uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
  -> EverMind MCP tools
  -> local memory, archive, and code graph layers
```

## ロードマップ

- 管理された環境向けの非対話セットアップを改善する。
- 大規模リポジトリ向けのアーカイブテンプレートを拡張する。
- MCP 起動失敗の診断を強化する。
- local-first を既定の運用モデルとして維持する。
- cloud memory は必須ではなく、将来の任意同期として扱う。

## Community and Support

Issues and pull requests are welcome. If EverMind helps your local AI memory workflow, a star or small contribution helps the project move forward.

<div align="center">
  <p><strong>EverMind community group</strong></p>
  <img src="png/EverMind3群.png" alt="EverMind community group QR code" width="260">
</div>

<div align="center">
  <p><strong>Support the project</strong></p>
  <img src="png/Alipay.jpg" alt="Alipay support QR code" width="220">
  <img src="png/wecha.png" alt="WeChat support QR code" width="220">
</div>
