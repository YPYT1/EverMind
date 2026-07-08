# MCP Config Templates

Copy the template for your platform and client. Replace `<EVERMIND_ROOT>` with the
absolute path to your EverMind clone (the only placeholder).

| File | Client | Platform |
|------|--------|---------|
| `claude-code.windows.json` | Claude Desktop | Windows |
| `claude-code.macos.json` | Claude Desktop | macOS |
| `cursor.windows.json` | Cursor | Windows |
| `cursor.macos.json` | Cursor | macOS |
| `codex.windows.toml` | Codex | Windows |
| `codex.macos.toml` | Codex | macOS |
| `devin.example.json` | Devin | Any |

Example (Windows, Claude Desktop):

```json
{
  "mcpServers": {
    "evermind": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\Users\\you\\EverMind\\mcp", "evermind-mcp"]
    }
  }
}
```

No API keys required. No extra environment variables needed.
The setup scripts (`scripts/setup-windows.ps1` and `scripts/setup-macos.sh`)
can auto-generate and install these configs for you.
