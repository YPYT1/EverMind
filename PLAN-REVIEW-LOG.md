# EverMind Plan Review Log

## Reviewer Infrastructure

- `codex exec` full-repository review timed out after 10 minutes without a verdict.
- A second targeted `codex exec` review timed out after 4 minutes without a verdict.
- Both commands were terminated by their timeout and made no repository changes.
- Review continued with one read-only Codex reviewer scoped to `PLAN.md` and named
  implementation files.

## Round 1

Verdict: `REVISE`

### Findings and responses

1. The 51-tool count retained cloud-only `list_workspaces`.
   - Accepted. The local-only target is now 50 tools. Both `cloud_info` and
     `list_workspaces` are excluded, and the 21 compatible local calls are listed.

2. The upstream Basic Memory lifespan reads OAuth state and starts broad runtime
   services.
   - Accepted with one refinement. The plan now uses a small local-only lifespan
     built from upstream public initialization and shutdown primitives. OAuth,
     cloud forcing, auto-update, and cloud routing are excluded. Local Markdown
     watching/index sync remains because it is part of complete local behavior.

3. EverMind's current Python/package metadata cannot execute Basic Memory.
   - Accepted. Phase 0 now raises the floor to Python 3.12, changes combined license
     metadata to AGPL, locks MCP/FastMCP dependencies, and requires a clean-runtime
     smoke test.

4. Legacy rollback would lose writes made after cutover.
   - Accepted. Legacy rollback is allowed only before write cutover. After cutover,
     failures recover forward on the new catalog; no dual-write layer is added.

5. The Basic Memory project-info resource template was omitted.
   - Accepted. The target and gates now include one static resource and one resource
     template, with enumeration and invocation checks.

6. Collapsing duplicate legacy IDs could break graph and event references.
   - Accepted. `legacy_memory_map` is now required before importing links/events,
     with foreign-key and idempotent re-import gates.

7. Mounting upstream while retaining manual archive code violates the non-growth
   constraint.
   - Accepted. Phase 4 deletes manual archive tools, schemas, and dispatch, removes
     the compatibility adapter before the gate, and forbids duplicate
     implementations.

8. Project identity normalization was underspecified.
   - Accepted. The plan now defines remote selection, SSH/HTTPS normalization,
     worktree/symlink/path-case handling, catalog UUID persistence, tombstones, and
     collision/worktree tests.

9. Always-present local vectors conflicted with asynchronous completion.
   - Accepted. Commit now durably records local-vector `pending`; FTS remains
     available, restart resumes work, and only successful generation marks `ready`.
     Model, dimensions, license, hash, and corpus are pinned before schema work.

10. Repository-wide coverage percentages encouraged low-value tests.
    - Accepted. Numeric repository quotas were replaced by executable branch gates
      for each critical failure surface plus complete C test execution.

### Additional edits from primary review

- Clarified that cloud sync is excluded but local Markdown watcher/index sync is
  retained.
- Added a pinned internal C invocation-protocol gate for the deprecated raw-JSON
  compatibility risk.
- Preserved divergent source importance/evidence during exact dedup.
- Added AGPL source-offer and bundled-model license/provenance requirements.

Round 1 final line: `VERDICT: REVISE`

## Round 2

Verdict: `REVISE`

### Findings and responses

1. Basic Memory project IDs/configuration were not connected to the authoritative
   unified catalog.
   - Accepted. The plan now requires `UnifiedProjectResolver`,
     `basic_project_bindings`, journaled project creation, argument transforms for
     project-aware Basic tools, and an end-to-end create/use/index/delete gate.

2. `create_memory_project(workspace=...)` could still enter cloud routing.
   - Accepted. Compatibility fields remain accepted, but any cloud selector returns
     structured `CLOUD_DISABLED` before upstream execution. Hostile-environment
     tests require zero network calls even with plausible credentials.

3. Global-readable memory semantics lacked executable acceptance criteria.
   - Accepted. Phase 3 now tests cross-project default recall, ranking-only project
     boost, identical eligibility for both legacy `all_spaces` values, and mandatory
     provenance. Phase 5 adds explicit `include_expired` behavior.

4. Model selection appeared in both Phase 0 and Phase 5.
   - Accepted. Candidate benchmarking and artifact selection now occur only in
     Phase 0. Phase 5 consumes the pinned model and dimensions.

Round 2 final line: `VERDICT: REVISE`

## Round 3

Verdict: `APPROVED`

The reviewer rechecked only the four remaining Round 2 blockers and confirmed:

1. Unified project bindings and the end-to-end project lifecycle are fully
   specified and covered by executable gates.
2. Cloud workspace selectors are rejected before upstream execution, with
   zero-network verification.
3. Global recall, provenance, legacy `all_spaces`, and expiration semantics have
   explicit acceptance criteria.
4. Embedding model selection occurs only in Phase 0; Phase 5 consumes the pinned
   artifact.

No remaining P0/P1 contradiction makes implementation unsafe or impossible.

Round 3 final line: `VERDICT: APPROVED`
