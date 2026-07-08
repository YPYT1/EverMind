# EverMind Tests

Run all EverMind integration tests:

```bash
uv run pytest -q tests
```

The suite covers:

- top-level project layout;
- JSON/TOML template parsing;
- external dependency lock metadata;
- env and unified `config/evermind.example.yaml`;
- docs for components, architecture, and local-to-cloud roadmap;
- docs for MCP tools and the non-expert user journey;
- public template path hygiene;
- `scripts/common/render-configs.py`;
- Windows `install-all.ps1 -SkipToolInstall` config generation;
- EverMind Archive CLI connectivity;
- evermind-code-graph CLI connectivity;
- Windows `check-all.ps1` full-stack check with dummy model keys;
- full `mcp` pytest suite.

The tests do not perform real external installation downloads. They assume
EverMind Archive and evermind-code-graph are already installed when connectivity
tests are run.


