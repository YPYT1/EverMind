# Quickstart: macOS

This guide sets up EverMind on macOS.

## Requirements

- macOS 13 or newer recommended.
- Git.
- Python 3.11 or newer.
- `uv`.
- Network access for first-time dependency installation.

Check the basics:

```bash
git --version
python3 --version
uv --version
```

## 1. Clone

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
```

## 2. Run Guided Setup

```bash
bash scripts/macos/configure.sh
```

The guided setup:

- creates local runtime folders;
- creates `.env`;
- renders MCP snippets into `generated/mcp-config`;
- installs or links EverMind skills into user skill folders;
- never overwrites existing Codex, Claude Code, Cursor, or Devin config.

For a complete bootstrap with checks:

```bash
bash scripts/macos/bootstrap.sh
```

If the external engines are already installed:

```bash
bash scripts/macos/install-all.sh --skip-tool-install
```

## 3. Fill Model Keys

Open `.env` and fill the model API keys:

```bash
${EDITOR:-nano} .env
```

Keep keys local and never commit `.env`.

## 4. Check The Stack

```bash
bash scripts/macos/check-all.sh
```

Successful checks should confirm:

- `.env` exists;
- `uv` is available;
- MCP bridge exists;
- skills and templates exist;
- runtime health endpoint responds, if started;
- EverMind Archive Engine is available;
- EverMind Code Graph Engine is available;
- generated MCP snippets exist.

## 5. Copy MCP Config

Use the generated snippet for your client:

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

Do not point the MCP command to an extra nested child directory. EverMind MCP lives directly under `mcp/`.

## 6. Start Runtime

For a terminal run:

```bash
bash scripts/macos/start-everos.sh
```

MCP is normally started by the agent client. Manual startup is only for testing:

```bash
bash scripts/macos/start-mcp.sh
```

## Default Paths

```text
<EVERMIND_ROOT>          = $HOME/EverMind
<EVEROS_ROOT>            = $HOME/.evermind/everos
<EVERMIND_ARCHIVE_ROOT>  = $HOME/.evermind/archive
<CODEX_CONFIG_TOML>      = $HOME/.codex/config.toml
```

`<EVEROS_ROOT>` is runtime data. It is not the EverMind repository and not a source checkout.

