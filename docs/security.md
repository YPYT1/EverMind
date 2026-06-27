# Security

EverMind is local-first, but local services and local memory still need careful handling.

## Safe Defaults

- Bind the local runtime to `127.0.0.1` unless you provide your own authentication gateway.
- Keep `.env` out of git.
- Use candidate-first archive writes.
- Review archive candidates before committing official notes.
- Treat the archive as project knowledge, not a secret store.

## Never Store Secrets

Do not store:

- API keys;
- tokens;
- passwords;
- cookies;
- private keys;
- session credentials;
- recovery codes;
- production database URLs with credentials.

If a setup requires a secret, document the variable name and where it should be placed, not the value.

## Local Service Exposure

The runtime health endpoint and memory API should remain local by default.

Recommended:

```text
host = 127.0.0.1
```

Avoid binding to `0.0.0.0` unless you understand the network exposure and provide an authentication layer.

## Archive Review

EverMind Archive is intentionally reviewed Markdown. Before committing a candidate:

1. check that it describes stable facts;
2. remove secrets and temporary logs;
3. verify file paths and commands;
4. keep topic files focused;
5. avoid copying large code blocks or full diffs.

## Publishing A Fork

Before publishing a fork:

- delete `.env`;
- delete `generated/`;
- delete caches;
- scan for private paths and secrets;
- keep `THIRD_PARTY_NOTICES.md`;
- keep `third_party.lock.yaml`.

