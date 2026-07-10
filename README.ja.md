<div align="center">

<img src="./png/everymind.png" alt="EverMind" width="420" />

**AIコーディングエージェントのためのローカルファースト6層メモリシステム。**  
ゼロ設定。ゼロクラウド依存。Claude Code、Cursor、Codexで動作。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-enabled-8E44AD?style=flat-square)](https://modelcontextprotocol.io/)
[![Local First](https://img.shields.io/badge/local--first-yes-2ECC71?style=flat-square)](docs/architecture.md)
[![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?style=flat-square)](#アーキテクチャ)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-supported-0078D4?style=flat-square)](scripts/setup-windows.ps1)
[![macOS](https://img.shields.io/badge/macOS-supported-000000?style=flat-square)](scripts/setup-macos.sh)

[クイックスタート](#クイックスタート) · [アーキテクチャ](#アーキテクチャ) · [MCPツール](#mcpツール) · [セットアップ](#セットアップ) · [ドキュメント](docs/README.md) · [English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

</div>

---

## EverMindとは？

EverMindは、AIコーディングエージェントにセッションを越えた永続的なメモリを提供します。MCPを介してClaude Code、Cursor、Codexに直接組み込まれ、クラウドも独立したサーバーもAPIキーも設定も不要で、リポジトリを指すだけで使えます。

メモリは人間が知識を保存する方法をモデルに6層で構成されています：自動期限切れの作業メモ、エピソード的イベント、意味的事実、手続き的知識、永久アーカイブ決定、エンティティ関係グラフ。適切な層は内容と重要度に基づいて自動的に選択されます。

## 課題

AIエージェントはセッション間ですべてを忘れます：

- モジュールが特定の方法で設計された理由
- プロジェクトを実際にビルドまたはテストするコマンド
- 既知のバグと機能した修正方法
- デプロイ手順と落とし穴
- 個人の好みとコーディング規約

EverMindは、エージェントがその知識を保存・取得できる信頼できる場所を提供することで、これを解決します。

## アーキテクチャ

```text
          Claude Code / Cursor / Codex
                     |
                  MCP (stdio)
                     |
           +-----------------------+
           |   EverMind v2 コア    |
           |                       |
           |  remember / recall    |
           |  forget  / briefing   |
           +-----------+-----------+
                       |
           +-----------v-----------+
           |   SQLite              |
           | (プロジェクトごとに   |
           |  1ファイル)           |
           |                       |
           |  レイヤー1: 作業      |  24時間自動期限切れ
           |  レイヤー2: エピソード|  イベントと発見
           |  レイヤー3: 意味      |  プロジェクト事実
           |  レイヤー4: 手続き    |  ハウツー知識
           |  レイヤー5: アーカイブ|  永久決定
           |  レイヤー6: グラフ    |  エンティティ関係
           |                       |
           |  FTS5 キーワード検索  |
           |  sqlite-vec KNN       |
           |  イベントログ         |
           +-----------------------+
```

ストレージ：`~/.evermind/<project-slug>.db` — プロジェクトごとに1つのSQLiteファイル、名前はgit remoteから自動検出。

## クイックスタート

### 1. クローン

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
```

### 2. セットアップスクリプトの実行

**Windows：**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

**macOS / Linux：**

```bash
bash scripts/setup-macos.sh
```

スクリプトはPython 3.11+をチェックし、uvがない場合はインストールし、依存関係を同期し、Claude DesktopとCursorを自動設定します。

### 3. 手動設定（オプション）

`claude_desktop_config.json`に追加：

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

`/path/to/EverMind`を実際のクローンパスに置き換えてください。これが唯一必要な変更です。

### 4. ベクトル検索を有効化（オプション、推奨）

```bash
cd mcp
uv pip install sqlite-vec sentence-transformers
```

これらがなくても、EverMindはFTS5キーワード検索を使用します。インストールすると、`recall()`はハイブリッドBM25 + ベクトルKNNを実行し、「認証モジュールについて何を決定したか」のような意味的クエリに大幅に優れています。

## MCPツール

EverMind は同じ `evermind` MCP サーバーから 42 個のツールを公開します：14 個のメモリツール、14 個の内蔵コードグラフツール、14 個の内蔵アーカイブツール。外部 Basic Memory CLI や codebase-memory バイナリは不要です。

| ツール | 目的 |
|--------|------|
| `remember(content, importance, tags)` | メモリに保存。importance: 0 = 作業(24h), 1 = 長期, 2 = 永久 |
| `update_memory(id, content, tags, meta)` | 誤ったメモリを同じ ID のまま修正し、検索・embedding・グラフ・briefing キャッシュを再構築 |
| `recall(query, limit, mode)` | ハイブリッドBM25 + 意味検索。gitからプロジェクトを自動検出 |
| `forget(id)` | IDでメモリを削除 |
| `briefing()` | セッションコンテキストをロード：このプロジェクトの最近の重要なメモリ |

メモリタイプはコンテンツから自動検出：バグ修正→エピソード、アーキテクチャ決定→意味、デプロイ手順→手続き。削除されたくないものには`importance=2`を設定します。

## セットアップ

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
```

スクリプトの機能：
- Python 3.11+、uv、gitをチェック
- uvが見つからない場合はインストールを提供
- mcpディレクトリで`uv sync`を実行
- Claude DesktopとCursorのMCP設定を自動更新
- `~/.evermind`メモリディレクトリを作成

### macOS

```bash
bash scripts/setup-macos.sh
```

Windowsと同じ手順、macOS設定パス（`~/Library/Application Support/Claude/`）を使用。

### 手動インストール

```bash
# 依存関係をインストール
uv sync --directory mcp

# オプション：ベクトル検索（推奨）
cd mcp && uv pip install sqlite-vec sentence-transformers
```

## メモリライフサイクル

| レイヤー | 保持期間 | 用途 |
|----------|----------|------|
| 作業 | 24時間 | 一時的なメモ、WIPコンテキスト |
| エピソード | 長期 | イベント、バグ修正、発見 |
| 意味 | 長期 | プロジェクトに関する事実 |
| 手続き | 長期 | デプロイ手順、ワークフロー、ハウツー |
| アーカイブ | 永久 | アーキテクチャ決定、永久ルール |
| グラフ | 永久 | エンティティ関係（フェーズ3） |

- `importance=0` — 作業レイヤー（デフォルト、24時間で期限切れ）
- `importance=1` — 長期レイヤー（コンテンツタイプで自動分類）
- `importance=2` — アーカイブレイヤー（削除されない）

## エージェント指示

`CLAUDE.md`または`AGENTS.md`に追加：

```markdown
## EverMind Memory

Call briefing() at session start to restore project context.
Call remember(content) for anything worth keeping across sessions.
Call recall(query) before starting work on a feature or bug.

importance=0: temporary working note (default)
importance=1: long-term memory
importance=2: permanent archive (architecture decisions, critical bugs)
```

## ドキュメント

- [アーキテクチャ](docs/architecture.md)
- [MCPツールリファレンス](docs/mcp-tools.md)
- [設定](docs/configuration.md)
- [Windowsクイックスタート](docs/quickstart-windows.md)
- [macOSクイックスタート](docs/quickstart-macos.md)
- [トラブルシューティング](docs/troubleshooting.md)
- [v2リデザインノート](docs/v2-redesign.md)

---

## コミュニティとサポート

<div align="center">

<img src="./png/EverMind3群.png" width="200" /><br/>
<sub>EverMindコミュニティグループ</sub>

</div>

<div align="center">

<img src="./png/wecha.png" width="200" /><br/>
<sub>WeChat</sub>

</div>

<div align="center">

<img src="./png/Alipay.jpg" width="200" /><br/>
<sub>コーヒーをおごる ☕</sub>

</div>

<div align="center">
AIツールに実際に物事を覚えてほしいエンジニアのために構築されました。
</div>
