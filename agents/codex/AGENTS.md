# EverMind Agent Instructions for Codex

Use EverMind as the local memory layer for coding tasks.

## Before Code Changes

1. Determine the project slug from the repository folder.
2. Read EverOS memory with `briefing(space_id="coding:<slug>")`.
3. Use `recall` for prior decisions, known pitfalls, runtime configuration, interfaces, and test practices.
4. If Basic Memory project notes exist, read the relevant topic files.
5. Verify remembered facts against real files before editing.

## During Work

- Keep changes focused on the user's request.
- Prefer existing project patterns.
- Use codebase-memory for architecture, call path, and impact analysis when useful.
- Do not store secrets or credentials in memory.

## After Meaningful Changes

Generate a Basic Memory candidate when the work changes architecture, module responsibilities, runtime configuration, interfaces, storage, testing, deployment, or known pitfalls.

Only commit official Basic Memory notes after explicit user confirmation.
