---
name: evermind
description: Umbrella skill for the EverMind local memory suite. Use when a task should read local memory first, search codebase context, and produce reviewed EverMind Archive candidates after meaningful project changes.
---

# EverMind Skill

EverMind connects four layers:

1. EverOS for fast local semantic memory.
2. EverMind MCP for agent tool access.
3. EverMind Archive for reviewed long-term project notes.
4. evermind-code-graph for code structure and impact analysis.

## Default Workflow

### Before work

1. Determine the project slug from the repository folder name.
2. Use `space_id = coding:<project-slug>`.
3. Call `briefing` for high-value context.
4. Use `recall` for decisions, pitfalls, configuration, interfaces, and test habits.
5. Read existing EverMind Archive project notes when available.
6. Verify memory against real files before making claims or edits.

### During work

- Search memory when a decision, module boundary, or old pitfall is uncertain.
- Use evermind-code-graph for architecture, call paths, and change impact.
- Do not save secrets, API keys, tokens, cookies, private keys, or session credentials.

### After work

When code, configuration, interfaces, test strategy, deployment, or architecture changed:

1. Summarize stable facts.
2. Include evidence: files, commands, test results, or service status.
3. Generate a EverMind Archive candidate.
4. Commit official notes only after explicit user confirmation.

Final implementation responses should include:

```text
Memory status:
- EverOS: updated / not updated / not applicable
- EverMind Archive candidate: generated / not generated / not applicable
- Official EverMind Archive notes: committed / pending confirmation / not committed
```



