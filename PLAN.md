# EverMind Local Source Fusion Completion Plan

## Objective

Ship one local-only EverMind MCP product that executes the vendored Basic Memory
and codebase-memory sources in process or as an internal bundled engine, exposes
one coherent project lifecycle, and passes reproducible release and memory-quality
gates.

The target surface is:

- 50 tools in one MCP registry.
- 3 Basic Memory prompts.
- 1 static Basic Memory resource (`memory://ai_assistant_guide`).
- 1 Basic Memory resource template (`memory://{project}/info`).
- No cloud tools, OAuth, cloud workspaces, cloud sync, or implicit uploads.
- No runtime dependency on external `basic-memory` or `codebase-memory-mcp`
  installations.
- No silent engine fallback in official builds.

The combined distribution is AGPL-3.0-or-later because vendored Basic Memory is
executed in the EverMind process.

The unified runtime requires Python 3.12 or newer. Runtime dependency versions,
including MCP and FastMCP, are locked from the pinned Basic Memory source instead
of relying on EverMind's former Python 3.11 and `mcp>=1.0` floor.

## Confirmed Product Semantics

### One unified project

- `project_id` identifies a logical project and owns memory and archive history.
- `workspace_id` identifies one repository checkout and owns one code graph index.
- Clones and worktrees of the same Git remote share `project_id` but retain
  independent `workspace_id` indexes.
- Repository display names are not identifiers and may be duplicated.
- Repositories without a Git remote receive a persisted UUID.

One `UnifiedProjectResolver` maps compatibility identifiers to the catalog:

- Basic Memory external IDs, names, and paths map to `project_id`.
- Codebase internal project keys map to `workspace_id`.
- Duplicate display names are resolved by stable ID or canonical path; an ambiguous
  bare name is an error and is never guessed.
- Project-aware Basic Memory tools pass through this resolver before executing the
  upstream function. The resolver changes identity arguments only and does not
  reimplement the tool's behavior.

`delete_project` accepts `project` and `project_name` as compatibility aliases for
the same project identifier. If both are supplied, they must normalize to the same
project. The operation detaches the unified project and removes derived Basic Memory
metadata/indexes and code graph indexes. It does not delete the repository, Markdown
archive, or durable EverMind memories.

### One global memory catalog

- All memories are readable and searchable by default.
- `project_id` records provenance and affects ranking, not authorization.
- Current-project memories receive a ranking boost; other projects remain eligible.
- Every result reports its source project or projects.
- Existing `all_spaces` remains accepted but no longer controls visibility.
- Expired memories are excluded unless `include_expired=true` is explicit.

### Deduplication and fact history

- Exact normalized content has a database-enforced global identity.
- Concurrent identical writes use `INSERT ... ON CONFLICT`.
- One memory can have multiple rows in `memory_sources` for project, tags,
  evidence, and first/last observation times.
- Semantic near-duplicates are suggestions only and never auto-merge.
- `update_memory` creates a new version and marks the old version superseded.
- Conflicting ordinary `remember` calls create a conflict set without replacing
  either claim.
- Retrieval prefers current, verified claims and surfaces unresolved conflicts.

### Semantic retrieval

- A bundled local multilingual embedding profile is always available.
- Each memory always receives a local baseline vector.
- When configured and healthy, an external embedding/rerank API is preferred.
- Local and external vectors are stored in separate versioned profiles.
- External timeout or circuit-breaker activation falls back to the local profile.
- The selected profile, coverage, latency, and fallback reason are observable.

## Unified MCP Composition

Use one FastMCP server and direct in-process registration instead of an external
MCP bridge or a mounted child server:

1. Create one FastMCP server and make it the only public transport.
2. Add a small local-only lifespan that reuses Basic Memory's public container,
   initialization, local file watcher/sync, and database shutdown primitives. It
   must not construct `CLIAuth`, honor cloud-forcing environment variables, run
   auto-update, or create cloud clients.
3. Register 20 upstream local Basic Memory tool functions through the unified
   project-argument resolver, excluding `cloud_info`, `list_workspaces`, and
   upstream `delete_project`. Wrap `create_memory_project` and
   `list_memory_projects` only where catalog coordination is required; do not copy
   their note/search behavior.
4. Register the 14 EverMind core-memory tools.
5. Register 13 codebase tools, excluding its `delete_project` registration.
6. Register the 2 reviewed-candidate tools.
7. Register one unified `delete_project` implementation.
8. Register the 3 upstream prompts, the assistant-guide resource, and the local
   project-info resource template.

The Basic Memory-compatible local surface is 21 calls: the 20 registered upstream
functions plus unified `delete_project`. The excluded upstream calls are
`cloud_info` and `list_workspaces`. The resulting count is 50 unique tools.

The 21-call compatibility checklist is: `build_context`, `canvas`,
`create_memory_project`, `delete_note`, unified `delete_project`, `edit_note`,
`fetch`, `list_directory`, `list_memory_projects`, `move_note`, `read_content`,
`read_note`, `recent_activity`, `release_notes`, `schema_diff`, `schema_infer`,
`schema_validate`, `search`, `search_notes`, `view_note`, and `write_note`.

Keep `server_v2.call_tool` as a compatibility adapter during migration, but make
the FastMCP registry the source of truth for schemas, protocol errors, prompts,
resources, and lifespan cleanup. Remove the adapter after all existing callers and
tests use the unified registry.

## Data Model and Migration

Add one versioned catalog database under `EVERMIND_HOME` with these minimum tables:

- `projects(project_id, remote_fingerprint, display_name, state, ...)`
- `workspaces(workspace_id, project_id, canonical_path, git_identity, ...)`
- `memories(..., normalized_hash, state, valid_from, valid_to, supersedes_id, ...)`
- `memory_sources(memory_id, project_id, workspace_id, tags, evidence, ...)`
- `memory_conflicts(conflict_id, claim_key, state, ...)`
- `memory_conflict_members(conflict_id, memory_id)`
- `embedding_profiles(profile_id, provider, model, version, dimensions, ...)`
- `memory_embeddings(memory_id, profile_id, vector, status, attempts, ...)`
- `project_operations(operation_id, kind, state, payload, completed_steps, ...)`
- `legacy_memory_map(source_db, legacy_id, memory_id)`
- `basic_project_bindings(project_id, basic_external_id, basic_name, basic_path)`

Migration requirements:

1. Discover every existing per-space SQLite database.
2. Acquire a cross-process migration lock and create an online backup before
   importing any row.
3. Import memories, graph links, events, and tags idempotently.
4. Preserve existing memory IDs where they do not collide and record every import
   in `legacy_memory_map` before importing graph links or events.
5. Convert exact duplicates to one memory plus multiple source rows.
6. Leave old databases untouched and readable until the release is accepted.
7. Record a migration completion marker only after integrity checks pass.
8. On restart before cutover, resume or roll back an interrupted migration from the
   operation log.
9. Verify foreign-key integrity, FTS row parity, graph references, event references,
   and idempotent re-import before accepting writes on the new catalog.

Do not delete legacy databases automatically. Rollback to legacy databases is
supported only before the new catalog accepts writes. After cutover, recovery is
roll-forward on the new catalog; the implementation does not dual-write. A later
explicit maintenance release may provide archival cleanup after at least one stable
release cycle.

## Implementation Phases

### Phase 0: Freeze baselines

- Capture the current 42-tool schemas and successful response fixtures.
- Preserve the existing pressure and retrieval datasets as runnable tests.
- Add regression tests for every confirmed defect before changing behavior.
- Record current file counts, third-party versions, source hashes, and binary hash.
- Update package metadata to AGPL-3.0-or-later and Python >=3.12, lock the local
  Basic Memory/FastMCP dependency set, and remove cloud-only dependencies where
  imports prove they are unnecessary.
- Add a clean Python 3.12 environment smoke test that imports and starts the local
  unified runtime without relying on the globally installed Basic Memory CLI.
- Benchmark local multilingual model candidates against the fixed English/Chinese
  corpus, select the smallest candidate meeting Hit@3 and MRR gates, then pin its
  dimensions, license, artifact hash, and corpus before creating the multi-profile
  vector schema.

Gate: every new regression test fails for the intended reason on the current tree.

### Phase 1: Security, protocol, and lifecycle

- Route candidate `project_slug`, `target_file`, and `candidate_id` through the
  existing slug and safe-child validation.
- Make application failures set MCP `isError=true` while retaining structured error
  fields.
- Add `MemoryService.close()` and stop briefing, embedding, database, and mounted
  Basic Memory lifespans deterministically.
- Replace stale archive lock age behavior with owner/PID-aware recovery where
  available and bounded stale-lock recovery otherwise.

Gate:

- No archive operation can escape its configured root.
- Unknown and failed tool calls are protocol errors.
- Repeated embedded service construction and shutdown leaves zero worker threads or
  open SQLite handles.
- Crash-lock recovery succeeds within the normal request timeout.

### Phase 2: Complete and verify vendored codebase source

- Pin the exact upstream commit and record it in a machine-readable manifest.
- Restore the omitted upstream tests and required fixtures into the source bundle.
- Change the Windows runner so missing test files and unexpected exit codes fail.
- Run `make -f Makefile.cbm test` and Windows product-surface guards.
- Change file-state persistence so a fingerprint is committed only after successful
  graph persistence.
- Keep failed files dirty with an explicit error and retry state.
- Key internal C projects by `workspace_id`, never display name.
- Pin and test the internal C invocation protocol so the adapter cannot silently
  break when the deprecated raw-JSON CLI form changes.

Gate:

- Native unit/integration tests execute rather than skip.
- Fault injection followed by an ordinary rebuild restores the failed file without
  deleting the project database.
- Index status cannot report complete while a file is failed or missing from graph
  persistence.
- Same-name repositories never overwrite one another.

### Phase 3: Unified project catalog and global memory migration

- Introduce project/workspace identity and the global catalog schema.
- Migrate existing per-space databases using the idempotent migration above.
- Implement atomic exact dedup and multi-source provenance.
- Implement the journaled unified `delete_project` operation.
- Implement journaled unified project creation and Basic binding so
  `create_memory_project`, `index_repository`, and all project-aware Basic tools
  converge on the same catalog record.
- Keep internal component deletion methods private for recovery and tests.
- Normalize SSH and HTTPS forms of the selected Git remote into one fingerprint:
  prefer `origin`, otherwise use the sole fetch remote, otherwise persist a UUID.
  Resolve worktree roots and symlinks, apply platform path-case normalization, and
  store the UUID in the global catalog rather than modifying the repository.
- Keep project rows as tombstones after detach so retained memories preserve
  readable provenance.
- Keep importance, tags, evidence, and observation times on `memory_sources`; use
  the highest active source importance for ranking instead of discarding divergent
  source metadata during exact dedup.

Gate:

- Four-process identical-write pressure creates one memory and all expected sources.
- Different projects with identical content retain all provenance.
- Interrupted migration and interrupted project deletion resume safely.
- Re-importing every legacy database produces no new memories, links, or events,
  and every legacy graph/event reference resolves through `legacy_memory_map`.
- No source repository, Markdown note, or durable memory is removed by
  `delete_project`.
- Same remote in different worktrees shares one `project_id`; different remotes
  with the same basename never share a project or workspace index.
- A create -> remember/archive -> code index -> unified delete workflow uses one
  `project_id`, preserves original data, and leaves both derived engines detached.
- `recall` without `all_spaces` can return another project's memory; the current
  project affects score only. `all_spaces=true` and `all_spaces=false` produce the
  same eligible catalog, and every result contains project provenance.

### Phase 4: Local Basic Memory source execution

- Vendor the complete pinned Basic Memory source and license files.
- Run the explicit local-only lifespan in process and register local tool functions
  without a namespace. Retain local Markdown watching/index sync, but do not run
  Basic Memory's OAuth checks, auto-update, cloud routing, or cloud sync.
- Remove `cloud_info` and `list_workspaces` registration rather than adding local
  replacements for cloud concepts.
- Retain upstream compatibility parameters such as `workspace`, but reject any
  non-empty cloud selector at the boundary with structured `CLOUD_DISABLED` before
  invoking upstream code.
- Replace the colliding delete registration with unified `delete_project`.
- Expose the three local prompts, assistant-guide resource, and project-info
  resource template.
- Make Basic Memory's SQLite index derived and rebuildable from Markdown; the global
  EverMind catalog remains authoritative for unified project identity.
- Delete EverMind's manual `_LOCAL_ARCHIVE_TOOLS`, `_fast_*` implementations,
  duplicate schemas, and duplicate dispatch in this same phase. Retain only the two
  reviewed-candidate tools and the minimal compatibility adapter until its callers
  move to FastMCP, then remove the adapter before the phase gate.
- Keep the resulting archive compatibility layer no larger than the manual archive
  implementation it replaces; do not maintain two implementations.

Gate:

- A real stdio client lists exactly 50 tools, 3 prompts, 1 static resource, and 1
  resource template.
- The 21 local Basic Memory-compatible calls match upstream local behavior and
  response semantics.
- `basic_memory.*` modules are demonstrably loaded and exercised.
- Poisoned PATH executables are never invoked.
- No cloud network call occurs even when inherited environment variables contain
  cloud credentials or `BASIC_MEMORY_FORCE_CLOUD=true`.
- Calling `create_memory_project(workspace=...)` with valid-looking cloud
  credentials returns `CLOUD_DISABLED` and performs zero network activity.
- Local Markdown file changes continue to update the derived Basic Memory index.

### Phase 5: Versioned facts and dual embedding profiles

- Add supersession, validity, verification, and conflict-set storage.
- Exclude superseded and expired claims from default recall and add an explicit
  `include_expired` compatibility field for intentional history queries.
- Add local and external embedding profile storage and background completion.
- Add provider health, circuit breaker, and per-profile retrieval metrics.
- Consume the model, dimensions, license, artifact hash, and corpus already selected
  and pinned by Phase 0; retain configurable batch size.
- Apply current-project boost without filtering other projects.
- Make memory commit record a durable local-vector `pending` row. FTS retrieval is
  available immediately, restart resumes pending work, and only a successfully
  generated vector changes the row to `ready`.

Gate:

- English and Chinese exact, paraphrase, and code-identifier datasets each achieve
  Hit@3 >= 95% and MRR >= 0.90.
- A newer verified value outranks an older value in 100% of conflict fixtures.
- Unresolved conflicts are explicitly surfaced.
- External-provider failure falls back to local retrieval without mixing vector
  spaces or failing the request.
- Every result includes project provenance.
- Expired memories appear only when `include_expired=true`.

### Phase 6: Reproducible full-product release

- Stop presenting the standalone wheel as a complete product.
- Build one complete bundle per supported OS/architecture containing Python runtime,
  EverMind, vendored Basic Memory, the codebase binary, model artifact, licenses,
  and a signed/hash manifest.
- Build a complete source bundle with vendored tests and reproducible build scripts.
- Update root/package license metadata, notices, source-offer instructions, and
  documentation for AGPL-3.0-or-later. Include license/provenance entries for the
  bundled embedding model and every third-party engine artifact.
- Verify runtime files against the manifest at startup.
- Fail startup if an official bundle is incomplete or its engine binary is invalid.
- Preserve configurable calibration for model batch size, API timeout, and codebase
  engine timeout.

Gate:

- Clean-machine install tests pass on Windows, macOS, and Linux.
- Source bundle rebuilds byte-identical or documented reproducible outputs.
- Official bundle never reports `source_integrated=false` or `native-python`
  fallback.
- Upgrade from the current layout preserves all memories and Markdown files.
- A failed pre-cutover migration reopens legacy databases without data loss; a
  post-cutover failure recovers forward on the new catalog without reverting to a
  stale legacy database.

## Verification Matrix

Every phase must keep these suites green:

- Python lint and format checks.
- Full MCP unit and integration suite.
- Real stdio positive calls for every listed tool.
- Schema-negative calls for every tool with input fields.
- Prompts and resources enumeration and invocation.
- C upstream tests and Windows product guards.
- Multi-process memory, archive, and code-index stress.
- Forced process termination and restart recovery.
- Wheel test retained only to prove it is not advertised as the full product.
- Platform-bundle clean install and upgrade tests.

Coverage policy:

- Every branch in path confinement, migration/cutover, exact dedup, project-operation
  recovery, protocol errors, provider failover, and lifecycle shutdown has an
  executable regression case.
- All C test targets are present and executed; no missing-test skip is accepted.
- Do not add low-value tests solely to raise a repository-wide percentage.

## Rollback and Stop Conditions

- Keep legacy databases and the old server entry point until migration and stdio
  compatibility tests pass.
- Each schema migration must have a backup and idempotent resume path. Legacy
  rollback is allowed only before the write cutover; after cutover use roll-forward
  recovery.
- Do not continue to the next phase with a known P0/P1 defect.
- Stop and revisit architecture if in-process Basic Memory composition requires
  duplicating its service layer or maintaining a fork larger than a small,
  documented registration patch.
- Do not claim 10-star status until every release, recovery, quality, and coverage
  gate has fresh evidence on all supported platforms.

## Explicit Non-Goals

- Basic Memory cloud tools and `cloud_info`.
- OAuth, cloud workspaces, background cloud sync, or uploads.
- Remote authorization or per-project read permissions.
- Automatic merging of semantic near-duplicates.
- Automatic deletion of legacy databases or original content.
- Standalone wheel parity with the complete product bundle.
