# Write Policy

EverMind uses layered persistence so automatic memory does not become automatic knowledge pollution.

## Level 0: Never Store

Do not store:

- API keys, tokens, passwords, cookies, private keys, or session credentials;
- low-value temporary logs;
- sensitive personal information not explicitly intended for memory.

## Level 1: EverOS Realtime Memory

Use EverOS for fast local semantic recall:

- current session context;
- short-term project facts;
- cross-session user preferences;
- codebase-memory query observations.

## Level 2: Basic Memory Candidate

Generate a reviewed candidate for durable project knowledge:

- architecture decisions;
- runtime configuration;
- storage and interface contracts;
- known pitfalls;
- test and verification practices;
- module responsibilities.

Candidates must include evidence such as file paths, commands, test results, or service status.

## Level 3: Official Basic Memory Notes

Official notes require explicit user confirmation. No agent should silently promote a candidate into official long-term project memory.

See `config/evermind.example.yaml` for the unified write policy and memory router example.
