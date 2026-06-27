# Configuration

EverMind keeps configuration simple by separating human-readable intent from runtime environment variables.

## Configuration Files

| File | Purpose | Commit it? |
| --- | --- | --- |
| `config/evermind.example.yaml` | Human-readable full-system reference. It explains paths, MCP, models, write policy, routing, and future sync placeholders. | Yes |
| `.env.example` | Environment variable template copied to `.env`. It is what scripts and MCP read at runtime. | Yes |
| `.env` | Local machine paths, API keys, and runtime values. | No |
| `generated/mcp-config/*` | Rendered snippets for Codex, Claude Code, Cursor, and Devin. | No |

`config/` intentionally contains one file. Multiple config files make first-time setup harder, so EverMind keeps the complete reference in `config/evermind.example.yaml`.

## Placeholder Reference

| Placeholder | What to fill in | Windows example | macOS example |
| --- | --- | --- | --- |
| `<EVERMIND_ROOT>` | The local path where this EverMind repository is cloned. It contains `README.md`, `skills/`, `agents/`, `templates/`, and `mcp/`. | `D:\Project\EverMind` | `$HOME/EverMind` |
| `<EVEROS_ROOT>` | Runtime data root. This is where local memory files, indexes, logs, and runtime config live. It is not the source-code directory. | `D:\EverMindMemory\everos` | `$HOME/.evermind/everos` |
| `<EVERMIND_ARCHIVE_ROOT>` | Reviewed EverMind Archive root. Official project notes live under `projects/<project-slug>/`; candidates live under `.candidates/`. | `D:\EverMindMemory\evermind-archive` | `$HOME/.evermind/archive` |
| `<EVEROS_REPO>` | Optional path to a runtime source checkout, only needed when running the runtime from source. | `D:\Project\EverOS` | `$HOME/src/EverOS` |
| `<CODEX_CONFIG_TOML>` | Codex config file where the `mcp_servers.evermind` snippet is pasted. | `%USERPROFILE%\.codex\config.toml` | `$HOME/.codex/config.toml` |
| `<project-slug>` | Lowercase project identifier used in `coding:<project-slug>` and `projects/<project-slug>/`. Usually the repository folder name. | `my-app` | `my-app` |

## Important Environment Variables

### Runtime Paths

```dotenv
EVERMIND_HOME=
EVEROS_ROOT=
EVERMIND_ARCHIVE_ROOT=
EVERMIND_ARCHIVE_CANDIDATE_DIR=
```

- `EVERMIND_HOME` is the parent folder for local EverMind data.
- `EVEROS_ROOT` is runtime data, not repository source code.
- `EVERMIND_ARCHIVE_ROOT` is reviewed Markdown knowledge.
- `EVERMIND_ARCHIVE_CANDIDATE_DIR` stores proposed updates before user confirmation.

### MCP

```dotenv
EVERMIND_MCP_BACKEND=everos
EVERMIND_MCP_DEFAULT_SPACE=
EVERMIND_MCP_USER_ID=mcp-user
EVERMIND_ARCHIVE_WRITE_POLICY=candidate
```

Use `candidate` as the default archive write policy. It lets agents propose durable notes without silently committing them.

### Models

```dotenv
EVEROS_LLM__MODEL=
EVEROS_LLM__API_KEY=
EVEROS_LLM__BASE_URL=

EVEROS_EMBEDDING__MODEL=
EVEROS_EMBEDDING__API_KEY=
EVEROS_EMBEDDING__BASE_URL=

EVEROS_RERANK__MODEL=
EVEROS_RERANK__API_KEY=
EVEROS_RERANK__BASE_URL=
```

Model keys belong in `.env` or your shell environment. Never paste API keys into MCP snippets, agent instructions, README files, or archive notes.

### Future Cloud Mode

```dotenv
EVERMIND_MEMORY_MODE=local
EVERMIND_SYNC_MODE=off
EVERMIND_CLOUD_BASE_URL=
EVERMIND_CLOUD_API_KEY=
```

These values are reserved for future local-to-cloud modes. v1 remains local-first.

## Generated MCP Config

Setup scripts render snippets into:

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

Generated snippets include local paths and should be treated as machine-specific output.

## Windows Path Note

Windows generated TOML uses `/` path separators such as `D:/Project/EverMind/mcp`. This avoids TOML string escaping problems with backslashes.

JSON snippets can safely use normal escaped Windows paths.

