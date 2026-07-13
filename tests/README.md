# EverMind Tests

Run all EverMind integration tests:

```bash
uv run pytest -q tests
```

The suite covers:

- top-level project layout;
- JSON/TOML template parsing;
- built-in engine defaults with no external engine switches;
- env and unified `config/evermind.example.yaml`;
- docs for components, architecture, and the local-only runtime boundary;
- docs for MCP tools and the non-expert user journey;
- public template path hygiene;
- `scripts/common/render-configs.py`;
- Windows `install-all.ps1` local config generation;
- no-required-external-CLI behavior for archive and code graph;
- Windows `check-all.ps1` full-stack check with dummy model keys;
- full `mcp` pytest suite.

The tests assert that setup does not download or require external archive/code
graph CLIs.


