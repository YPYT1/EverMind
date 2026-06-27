# Troubleshooting

This guide lists common setup and runtime problems.

## Port 3378 Is Not Listening

Symptoms:

- health check fails;
- `check-all` warns that the runtime endpoint did not respond;
- `briefing` or `recall` cannot reach the backend.

Try:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\start-everos.ps1
```

```bash
bash scripts/macos/start-everos.sh
```

Then check:

```text
http://127.0.0.1:3378/health
```

## MCP Tool Times Out

Check:

- `uv` is installed and on PATH;
- the MCP command points to `<EVERMIND_ROOT>/mcp`;
- the command is `evermind-mcp`;
- `.env` exists;
- runtime base URL is correct.

Manual test:

```text
uv run --directory <EVERMIND_ROOT>/mcp evermind-mcp
```

## Agent Does Not See EverMind Tools

Try:

1. restart the agent client;
2. open a new session;
3. verify the MCP snippet was pasted in the right config file;
4. check whether the client requires JSON or TOML;
5. run the platform `check-all` script.

## Archive Notes Are Not Written

This is often expected. EverMind uses candidate-first writes.

Check:

- `EVERMIND_ARCHIVE_WRITE_POLICY=candidate`;
- candidate directory exists;
- the agent called `propose_basic_memory_update`;
- official commit was explicitly confirmed.

Official notes should not be written silently.

## Skills Are Not Loaded

Some clients cache skill metadata.

Try:

- restart the client;
- check `~/.agents/skills`;
- check `~/.codex/skills` if using Codex;
- check `~/.claude/skills` if using Claude;
- rerun setup with copy mode if symlinks are unavailable.

Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\setup-user.ps1 -CopyInsteadOfSymlink
```

## Windows TOML Path Problems

If Codex rejects a TOML snippet, check for unescaped backslashes.

Use generated snippets from:

```text
generated/mcp-config/codex.toml
```

Generated Windows TOML uses `/` path separators to avoid invalid escapes.

## Model Key Checks Fail

Open `.env` and fill the required keys:

```text
EVEROS_LLM__API_KEY=
EVEROS_EMBEDDING__API_KEY=
EVEROS_RERANK__API_KEY=
```

Only fill keys for providers you actually use. Never paste keys into README, docs, or agent instructions.

