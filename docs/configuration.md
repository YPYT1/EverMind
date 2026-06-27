# Configuration

EverMind templates use placeholders so the repository can stay portable across Windows and macOS.

## Placeholder Reference

| Placeholder | What to fill in | Windows example | macOS example |
| --- | --- | --- | --- |
| `<EVERMIND_ROOT>` | The local path where this EverMind repository is cloned. It contains `README.md`, `skills/`, `agents/`, `templates/`, and `mcp/`. | `D:\Project\EverMind` | `$HOME/EverMind` |
| `<EVEROS_ROOT>` | The EverOS runtime data root. This is where EverOS stores local memory files, indexes, logs, and runtime config. It is not the EverOS source-code directory. | `D:\EverMindMemory\everos` | `$HOME/.evermind/everos` |
| `<BASIC_MEMORY_ROOT>` | The reviewed Basic Memory archive root. Official project notes live under `projects/<project-slug>/`; candidates live under `.candidates/`. | `D:\EverMindMemory\basic-memory` | `$HOME/BasicMemory` |
| `<EVEROS_REPO>` | Optional path to the EverOS source checkout, only needed when running EverOS from source instead of an installed package. | `D:\Project\EverOS` | `$HOME/src/EverOS` |
| `<CODEX_CONFIG_TOML>` | The Codex config file where the `mcp_servers.evermemos` snippet is pasted. | `%USERPROFILE%\.codex\config.toml` | `$HOME/.codex/config.toml` |
| `<project-slug>` | A lowercase project identifier used in `coding:<project-slug>` and `projects/<project-slug>/`. Usually the repository folder name. | `my-app` | `my-app` |

## Common Values

For a simple Windows setup:

```text
<EVERMIND_ROOT>       = D:\Project\EverMind
<EVEROS_ROOT>         = D:\EverMindMemory\everos
<BASIC_MEMORY_ROOT>   = D:\EverMindMemory\basic-memory
```

For a simple macOS setup:

```text
<EVERMIND_ROOT>       = $HOME/EverMind
<EVEROS_ROOT>         = $HOME/.evermind/everos
<BASIC_MEMORY_ROOT>   = $HOME/BasicMemory
```

## Important Distinctions

- `EVEROS_ROOT` is runtime data, not source code.
- `BASIC_MEMORY_ROOT` is reviewed project documentation, not vector index storage.
- Model API keys belong in `.env`, local shell environment, or EverOS runtime config; never paste them into MCP snippets.
- MCP snippets should contain only connection and local path settings.

## Unified Config File

`config/` intentionally keeps one readable file:

```text
config/evermind.example.yaml
```

It explains the full system in one place: runtime paths, EverOS API, MCP, model providers, external components, local-to-cloud sync placeholders, write policy, and memory routing.

Use `.env.example` for actual environment variables and secrets. Use `config/evermind.example.yaml` as the human-readable system configuration reference.

## Why `.env.example` Still Exists

`config/evermind.example.yaml` is for humans. It explains the full system in one place.

`.env.example` is for processes. It becomes `.env`, and scripts/MCP read runtime values from environment variables.

Keep secrets in `.env` or your shell environment, not in `config/evermind.example.yaml`.
