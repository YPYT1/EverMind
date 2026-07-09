# Configuration

EverMind v2 requires zero configuration for basic keyword search. For production retrieval quality, configure the SiliconFlow model stack in the local `.env` file at the EverMind repository root.

## Minimum Config (required)

Add this to your Claude Desktop `claude_desktop_config.json` or Cursor `mcp.json`:

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

Replace `/path/to/EverMind` with the absolute path to your EverMind clone.

Windows path example: `C:\\Users\\you\\EverMind`

That's it. Everything else is auto-detected:
- **Project space**: detected from `git remote get-url origin` → `coding:<repo-slug>`
- **Database location**: `~/.evermind/<slug>.db`
- **Search mode**: FTS5 by default; hybrid if sqlite-vec is installed

## Optional Environment Variables

Set these in `.env`. Keep MCP config focused on starting the server process.

| Variable | Default | What it does |
|----------|---------|--------------|
| `EVERMIND_HOME` | `~/.evermind` | Directory where SQLite databases are stored |
| `EVERMIND_DEFAULT_SPACE` | auto from git | Override project space (e.g. `coding:my-app`) |
| `EVERMIND_SILICONFLOW_API_KEY` | none | API key for SiliconFlow-compatible embedding, rerank, and LLM calls |
| `EVERMIND_SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` | SiliconFlow OpenAI-compatible endpoint |
| `EVERMIND_EMBED_PROVIDER` | `auto` | `siliconflow` for API embeddings, `local` for sentence-transformers |
| `EVERMIND_EMBED_MODEL` | `Qwen/Qwen3-Embedding-8B` | Embedding model |
| `EVERMIND_EMBED_DIM` | `512` | Embedding dimensions stored in sqlite-vec |
| `EVERMIND_EMBED_ENABLED` | `true` | Set to `false` to disable embedding entirely |
| `EVERMIND_RERANK_ENABLED` | `true` | Enable cross-encoder rerank after FTS + dense recall |
| `EVERMIND_RERANK_MODEL` | `Qwen/Qwen3-Reranker-8B` | Reranker model |
| `EVERMIND_RERANK_CANDIDATES` | `30` | Number of fused candidates sent to rerank |
| `EVERMIND_RECALL_MIN_SCORE` | `0.15` | Minimum final recall score when rerank succeeds or `min_score` is passed explicitly |
| `EVERMIND_LLM_ENABLED` | key present | Enable optional LLM features |
| `EVERMIND_LLM_MODEL` | `deepseek-ai/DeepSeek-V4-Flash` | LLM model for optional briefing summaries |
| `EVERMIND_LLM_BRIEFING_SUMMARY` | `false` | Add an LLM-generated summary to `briefing()` |
| `EVERMIND_AUTO_REINDEX_ON_START` | `false` | Rebuild FTS on startup with the current tokenizer |
| `EVERMIND_SENSITIVE_MEMORY_BLOCK` | `true` | Reject memory writes containing API keys, tokens, passwords, or private keys |

## Enable Production Retrieval

```bash
cd /path/to/EverMind/mcp
uv sync --extra full
```

Create a local `.env` at the EverMind repository root:

```bash
EVERMIND_SILICONFLOW_API_KEY=sk-...
EVERMIND_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
EVERMIND_EMBED_PROVIDER=siliconflow
EVERMIND_EMBED_MODEL=Qwen/Qwen3-Embedding-8B
EVERMIND_EMBED_DIM=512
EVERMIND_RERANK_ENABLED=true
EVERMIND_RERANK_MODEL=Qwen/Qwen3-Reranker-8B
EVERMIND_LLM_ENABLED=true
EVERMIND_LLM_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

After this, `recall()` uses FTS BM25 + dense vector search, fuses candidates with RRF, and reranks the top candidates when SiliconFlow is available.

## MCP Config Templates

Ready-to-use config files are in `templates/mcp-config/`:

| File | Platform | Client |
|------|---------|--------|
| `claude-code.windows.json` | Windows | Claude Desktop |
| `claude-code.macos.json` | macOS | Claude Desktop |
| `cursor.windows.json` | Windows | Cursor |
| `cursor.macos.json` | macOS | Cursor |
| `codex.windows.toml` | Windows | Codex |
| `codex.macos.toml` | macOS | Codex |
| `devin.example.json` | Any | Devin |

Replace `<EVERMIND_ROOT>` with your actual EverMind clone path.
