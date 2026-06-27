---
name: evermind-archive
description: Maintain reviewed, human-readable project knowledge in EverMind Archive. Use for initializing, updating, restructuring, or proposing durable project notes.
---

# EverMind Archive Skill

EverMind Archive stores reviewed long-term project knowledge as Markdown files.

## Rules

- Use human-readable project notes, not chat summaries.
- Split knowledge by topic; do not put everything in one file.
- Write stable facts only.
- Include evidence for code facts.
- Never store secrets, tokens, cookies, passwords, private keys, or session credentials.
- Use candidate-first writes. Official notes require explicit confirmation.

## Standard Files

Each project should maintain:

- `项目概览.md`
- `目录结构.md`
- `模块实现.md`
- `运行与配置.md`
- `数据与存储.md`
- `接口与通信.md`
- `测试与验证.md`
- `已知坑点.md`
- `修改记录.md`
- `待办事项.md`

Large modules should use `模块-<中文模块名>.md`.

## Candidate Format

Every durable update should contain:

- Reason: why this belongs in long-term memory.
- Evidence: paths, commands, tests, or service checks.
- Content: the note text to append or create.


