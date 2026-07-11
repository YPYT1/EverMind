# Third-party Source Fusion

EverMind vendors selected upstream source trees so users can clone one repository
and use one local MCP without installing separate MCP services. Because Basic
Memory is executed in process, the combined EverMind distribution is licensed
under AGPL-3.0-or-later. The root `LICENSE` contains the complete terms.

## codebase-memory-mcp

- Path: `third_party/codebase-memory-mcp`
- License: MIT
- Upstream commit: `c3bee33d543a592c63aebf11333090c37868c1c6`
- Use: bundled C code graph backend with tree-sitter grammars and Hybrid-LSP.
- Build output under `build/` is generated and should not be committed.
- Bundled build dependency: `third_party/codebase-memory-mcp/vendored/zlib`
  (zlib license) is compiled in so users do not need a system zlib package.

## basic-memory

- Path: `third_party/basic-memory`
- License: AGPL-3.0-or-later
- Upstream commit: `0e59bbffaf7dbca8f0507d1c8cc15033332670ee`
- Use: local archive tools, prompts, resources, Markdown indexing, and project
  behavior executed in the EverMind process.

## Offline embedding model

- Path: `third_party/models/multilingual-e5-small`
- Model: `intfloat/multilingual-e5-small`
- Revision: `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- License: MIT
- Use: mandatory local English and Chinese semantic retrieval baseline.

Exact source hashes, overlays, binary provenance, model hashes, and retrieval
metrics are recorded in `third_party/source-manifest.json` and
`third_party/model-manifest.json`. Component directories retain their upstream
license and notice files.

## Corresponding source

From a clean checkout with Git LFS content materialized, create the versioned
source archive and SHA-256 sidecar with:

```bash
uv run --frozen --directory mcp python -m scripts.release_source_bundle \
  --output-directory dist
```

The archive contains every Git-tracked source file, vendored test and fixture,
build script, model artifact, license, and manifest from the current commit. The
command rejects modified tracked files and unresolved Git LFS pointers.
