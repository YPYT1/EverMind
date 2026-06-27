# MCP Config Snippets

[English](README.md) | [Chinese](README.zh-CN.md)

These snippets are provided for quick `evermemos-mcp` integration.

## Usage
1. Copy the JSON snippet for your MCP client
2. Replace `YOUR_KEY` with your real `EVERMEMOS_API_KEY`
3. Release snippets use `uvx evermemos-mcp@latest`; use `from-source.json` only when you want a local checkout
4. For the local EverOS + Basic Memory fork, use the `*-everos-local.json` snippets. They point to `<EVERMIND_ROOT>\mcp` and `http://127.0.0.1:3378`.

## Files
- `claude-code.json`
- `claude-code-everos-local.json`
- `codex-everos-local.json`
- `cursor.json`
- `cursor-everos-local.json`
- `cline.json`
- `from-source.json`


Local EverOS + Basic Memory snippets must not contain LLM, embedding, or rerank keys; keep those secrets in `<EVEROS_ROOT>\everos.toml` or local environment variables only.



