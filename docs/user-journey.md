# User Journey

This is the intended non-expert flow from download to daily use.

## Goal

A user should be able to:

1. download EverMind;
2. run one setup command;
3. paste one MCP snippet into their agent;
4. ask the agent to start with memory;
5. receive archive candidates after meaningful work.

They should not need to understand every internal component on day one.

## 1. Download EverMind

```bash
git clone https://github.com/YPYT1/EverMind.git
cd EverMind
```

## 2. Configure

Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\configure.ps1
```

macOS:

```bash
bash scripts/macos/configure.sh
```

Configure asks for:

- local memory directory;
- model API keys, if you want to fill them immediately;
- whether to install/link user skills.

It creates:

- `.env`;
- local runtime folders;
- generated MCP snippets;
- user skill links or copies.

For a one-command bootstrap with checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1
```

```bash
bash scripts/macos/bootstrap.sh
```

## 3. Review `.env`

Open `.env` and check:

- local paths are correct;
- model keys are filled;
- `EVERMIND_MCP_BACKEND=everos`;
- `EVERMIND_ARCHIVE_WRITE_POLICY=candidate`.

`.env.example` exists because runtime processes need environment variables. `config/evermind.example.yaml` exists because humans need a readable full-system reference.

## 4. Copy One MCP Config

Use the generated file for your client:

```text
generated/mcp-config/codex.toml
generated/mcp-config/claude-code.json
generated/mcp-config/cursor.json
generated/mcp-config/devin.json
```

The MCP command should point to:

```text
<EVERMIND_ROOT>/mcp
```

Do not point it to an extra nested MCP child directory.

## 5. Start The Runtime

Start the local runtime before relying on memory search.

Windows terminal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\start-everos.ps1
```

Windows service with NSSM:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\install-everos-nssm.ps1 -NssmPath C:\path\to\nssm.exe -StartNow
```

macOS:

```bash
bash scripts/macos/start-everos.sh
```

MCP itself is usually started by the agent client from MCP config.

## 6. Use It In An Agent

At the beginning of work:

```text
Use EverMind. Start with briefing for this project, then recall known pitfalls.
```

During work:

```text
Search EverMind for previous decisions about this module.
```

After meaningful work:

```text
Create an EverMind Archive candidate with the stable facts and verification results.
```

After reviewing a candidate:

```text
Commit this archive candidate to the official project notes.
```

## Skill Install Locations

EverMind installs skills for the user, not only for this repository:

```text
~/.agents/skills
~/.codex/skills    when ~/.codex exists
~/.claude/skills   when ~/.claude exists
```

The setup script links by default and copies when linking is not possible.

## What Success Looks Like

A healthy setup has:

- an `.env` file;
- generated MCP snippets;
- skills in user skill folders;
- local runtime responding on the configured base URL;
- archive candidate directory created;
- agent can call `briefing` and `recall`;
- official archive writes require explicit confirmation.

