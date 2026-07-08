---
name: project-memory
description: Initialize a new project's memory in EverMind. Use when opening a repository for the first time and briefing() returns empty (memory_count=0).
---

# Project Memory Initialization Skill

Use when `briefing()` returns `memory_count = 0` — the project has no memory yet.

## Initialization Steps

### 1. Explore the codebase

```
evermind-code-graph cli index_repository '{"repo_path":"<absolute path to repo>"}'
evermind-code-graph cli get_architecture '{"project":"<project-slug>"}'
```

### 2. Seed core memories

Save these in order. Use `importance=1` for regular facts, `importance=2` for permanent architecture decisions.

```
remember("Tech stack: <languages, major frameworks, databases>", importance=1)
remember("Entry point: <main file and how to run it>", importance=1)
remember("Build: <command>  Test: <command>  Lint: <command>", importance=1)
remember("Package manager: <npm/pip/cargo/etc> — install with: <command>", importance=1)
remember("Key modules: <module A does X, module B does Y, ...>", importance=1)
remember("Environment: <required env vars and where .env.example is>", importance=1)
```

### 3. Save architecture decisions as archive

For each significant design decision you discover:

```
remember("Architecture: <decision and rationale>", importance=2)
```

## After Initialization

Call `briefing()` again to verify the memories were stored. You should see `memory_count >= 4`.

## Project Note Structure (optional reference format)

When writing remember() content for long-term memories, cover:

- **Purpose**: what this area is responsible for
- **Entry points**: files, commands, functions, or routes
- **Data flow**: inputs, outputs, state, external deps
- **Change risks**: what future changes might break
- **Evidence**: paths, commands, test results that verify the fact
