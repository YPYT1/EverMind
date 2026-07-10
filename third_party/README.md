# Third-party Source Fusion

EverMind vendors selected upstream source trees so users can clone one repository
and use one MCP without installing separate MCP binaries.

## codebase-memory-mcp

- Path: `third_party/codebase-memory-mcp`
- License: MIT
- Use: source-fused code graph backend with tree-sitter grammars and Hybrid-LSP.
- Build output under `build/` is generated and should not be committed.
- Bundled build dependency: `third_party/codebase-memory-mcp/vendored/zlib`
  (zlib license) is compiled in so users do not need a system zlib package.

## basic-memory

- Path: `third_party/basic-memory`
- License: AGPL-3.0-or-later
- Use: source-fused local archive semantics, Markdown parsing references, MCP
  tool contract, and project/archive behavior.
- Commercial boundary: distributing a build that incorporates or modifies this
  source must honor AGPL-3.0-or-later obligations. Keep this source and its
  license notices available with EverMind distributions.
