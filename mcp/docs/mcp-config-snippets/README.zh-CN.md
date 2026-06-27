# MCP 配置片段

[English](README.md) | [简体中文](README.zh-CN.md)

这些片段用于快速接入 `evermemos-mcp`。

## 使用说明

1. 按你的客户端复制对应 JSON
2. 把 `YOUR_KEY` 替换为真实 `EVERMEMOS_API_KEY`
3. 发布版片段默认使用 `uvx evermemos-mcp@latest`；只有本地源码联调时才改用 `from-source.json`
4. 本地 EverOS + Basic Memory 融合版使用 `*-everos-local.json`；这些片段固定指向 `<EVERMIND_ROOT>\mcp` 和 `http://127.0.0.1:3378`

## 文件列表

- `claude-code.json`
- `claude-code-everos-local.json`
- `codex-everos-local.json`
- `cursor.json`
- `cursor-everos-local.json`
- `cline.json`
- `from-source.json`


本地 EverOS + Basic Memory 片段不包含任何 LLM、embedding 或 rerank 密钥；这些密钥只允许放在 `<EVEROS_ROOT>\everos.toml` 或本机环境变量。



