# Skills

EverMind skills teach agents how to use the memory system consistently.

## Included Skills

| Skill | Purpose |
| --- | --- |
| `evermind` | Umbrella workflow for local memory. Recommended default. |
| `evermind-archive` | Reviewed long-term project notes. |
| `evermind-code-graph` | Architecture, search, call paths, snippets, and impact analysis. |
| `project-memory` | Initialization and restructuring of project memory files. |

## What The Umbrella Skill Does

The umbrella skill tells the agent to:

1. read memory before meaningful work;
2. use realtime recall for task-specific context;
3. use code graph analysis when repository structure or impact is unclear;
4. create archive candidates after meaningful changes;
5. avoid storing secrets;
6. verify remembered facts in real files before editing.

## Installation

Setup scripts install or link skills into user-level folders:

```text
~/.agents/skills
~/.codex/skills
~/.claude/skills
```

The script only installs into client folders that exist. It does not overwrite unrelated user skills.

## Customization

For a team or personal fork, customize:

- project-specific memory spaces;
- archive file naming conventions;
- write policy strictness;
- agent-specific final response requirements.

Keep the candidate-first archive rule unless you intentionally want fully automatic long-term documentation writes.

