# EverMind 中文文档

这里是 EverMind 的完整用户和维护者文档入口。

## 先从这里开始

| 文档 | 适用场景 |
| --- | --- |
| [Windows 快速开始](quickstart-windows.md) | 在 Windows 上安装和配置 EverMind。 |
| [macOS 快速开始](quickstart-macos.md) | 在 macOS 上安装和配置 EverMind。 |
| [用户路径](user-journey.md) | 想按非开发者视角理解完整安装和日常使用流程。 |
| [配置说明](configuration.md) | 需要理解 `.env`、占位符、模型 key 或运行路径。 |
| [工具集成](integrations.md) | 想接入 Codex、Claude Code、Cursor 或 Devin。 |

## 核心概念

| 文档 | 主题 |
| --- | --- |
| [架构](architecture.md) | 三层架构和记忆生命周期。 |
| [组件说明](components.md) | Runtime、MCP、Archive、Code Graph 和合规边界。 |
| [MCP 工具](mcp-tools.md) | agent 能调用哪些工具，以及什么时候用。 |
| [Skills](skills.md) | EverMind skills 如何约束 agent 的记忆行为。 |
| [写入策略](write-policy.md) | 哪些内容自动写、哪些生成候选、哪些禁止落库。 |
| [本地到云路线图](local-to-cloud-roadmap.md) | 未来云记忆模式和 v1 本地优先边界。 |

## 运维与排障

| 文档 | 主题 |
| --- | --- |
| [安全](security.md) | secrets、本地服务、档案审核和默认安全策略。 |
| [排障](troubleshooting.md) | 常见安装和运行问题。 |

## 推荐阅读顺序

1. 先读仓库 README，建立整体概念。
2. 按你的系统阅读 Windows 或 macOS 快速开始。
3. 把生成的 MCP snippet 复制到对应 agent。
4. 阅读 [MCP 工具](mcp-tools.md)，了解 agent 可以调用哪些能力。
5. 在允许写入正式长期档案前，阅读 [写入策略](write-policy.md)。

