# Security

EverMind is local-first, but local services and local memory still need careful handling.

## Safe Defaults

- Bind the local runtime to `127.0.0.1` unless you provide your own authentication gateway.
- Keep `.env` out of git.
- Use `importance=0` or `importance=1` for routine memories. Reserve `importance=2` for decisions and rules you want permanent.
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

## Permanent Archive Writes

In v2 there is no separate propose/commit workflow. When you call `remember(importance=2)`, the memory goes directly into the archive layer and is never deleted.

Use `importance=2` only for stable facts you are confident in:

- verify the content before saving;
- do not save secrets, temporary logs, or guesses;
- keep entries focused — one decision or pattern per call.

## Publishing A Fork

Before publishing a fork:

- delete `.env`;
- delete `generated/`;
- delete caches;
- scan for private paths and secrets;
- verify README links and setup commands;
- run tests before pushing.
