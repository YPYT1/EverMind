# EverMind Documentation

This directory is the complete user and maintainer documentation for EverMind.

## Start Here

| Document | Use it when |
| --- | --- |
| [Windows Quickstart](quickstart-windows.md) | You are setting up EverMind on Windows. |
| [macOS Quickstart](quickstart-macos.md) | You are setting up EverMind on macOS. |
| [User Journey](user-journey.md) | You want the full non-expert setup and daily-use flow. |
| [Configuration](configuration.md) | You need to understand `.env`, placeholders, model keys, or runtime paths. |
| [Integrations](integrations.md) | You want to connect Codex, Claude Code, Cursor, or Devin. |

## Concepts

| Document | Topic |
| --- | --- |
| [Architecture](architecture.md) | The three-layer design and memory lifecycle. |
| [Components](components.md) | Runtime, MCP, Archive, Code Graph, and compliance boundary. |
| [MCP Tools](mcp-tools.md) | The tools exposed to agents and when to use each one. |
| [Skills](skills.md) | How EverMind skills shape agent behavior. |
| [Write Policy](write-policy.md) | Which facts are stored automatically, proposed for review, or blocked. |
| [Local to Cloud Roadmap](local-to-cloud-roadmap.md) | Future cloud modes and the v1 local-first boundary. |

## Operations

| Document | Topic |
| --- | --- |
| [Security](security.md) | Secrets, local services, archive review, and safe defaults. |
| [Troubleshooting](troubleshooting.md) | Common setup and runtime problems. |

## Recommended Reading Order

1. Read the README for the high-level mental model.
2. Follow the quickstart for your platform.
3. Copy the generated MCP snippet for your agent.
4. Read [MCP Tools](mcp-tools.md) so you know what the agent can call.
5. Read [Write Policy](write-policy.md) before allowing official long-term archive writes.

