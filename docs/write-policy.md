# Write Policy

EverMind uses layered persistence so automatic memory does not become automatic knowledge pollution.

The policy has four levels.

## Level 0: Never Store

Do not store:

- API keys;
- tokens;
- passwords;
- cookies;
- private keys;
- session credentials;
- low-value temporary logs;
- unrelated personal information;
- unverified guesses that look like facts.

If a secret is involved, record only the safe fact that a configuration exists and where it belongs. Do not record the secret value.

## Level 1: Realtime Memory

Use realtime memory for fast local recall:

- current session context;
- short-term project facts;
- user preferences;
- decisions that help the next task;
- useful code graph observations that have been verified in files.

Realtime memory is useful but should not be treated as official documentation.

## Level 2: EverMind Archive Candidate

Generate a reviewed candidate for durable project knowledge:

- architecture decisions;
- runtime configuration;
- storage and interface contracts;
- known pitfalls;
- test and verification practices;
- module responsibilities;
- meaningful task outcomes.

Candidates must include evidence:

- file paths;
- commands;
- test results;
- service status;
- configuration names;
- affected modules.

## Level 3: Official EverMind Archive Notes

Official notes require explicit user confirmation. No agent should silently promote a candidate into official long-term project memory.

Official archive notes should be:

- stable;
- useful to future work;
- written in clear project documentation style;
- organized by topic;
- free of secrets.

## Default Behavior

EverMind defaults to:

```dotenv
EVERMIND_ARCHIVE_WRITE_POLICY=candidate
```

That means agents can propose durable notes, but the user stays in control of official long-term knowledge.

## Router Examples

| Input | Default route |
| --- | --- |
| Temporary log output | Level 0 or ignore |
| User preference | Level 1 |
| Verified project fact | Level 1 and possibly Level 2 |
| Architecture decision | Level 2 |
| Test command and result | Level 2 |
| API key or token | Level 0 |
| Final reviewed project note | Level 3 |

See `config/evermind.example.yaml` for the unified write policy and memory router example.

