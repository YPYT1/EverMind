---
name: project-memory
description: Initialize or restructure a project's long-term memory files, including directory maps, module notes, configuration, tests, pitfalls, and change records.
---

# Project Memory Skill

Use when creating a new project memory archive or reorganizing existing notes.

## Initialization Order

1. `目录结构.md`
2. `模块实现.md`
3. `运行与配置.md`
4. `数据与存储.md`
5. `接口与通信.md`
6. `测试与验证.md`
7. `已知坑点.md`
8. `项目概览.md`
9. `修改记录.md`
10. `待办事项.md`

## Split Module Notes When

- A module has its own entrypoint, state, data flow, or external dependency.
- The module is likely to be changed independently later.
- The note becomes too large to scan quickly.

## Evidence

Every note should cite files, commands, or test results. If something is not verified, mark it as `未验证`.

