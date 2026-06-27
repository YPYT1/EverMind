# Local To Cloud Roadmap

EverMind is local-first. Cloud memory is an optional future adapter, not a required dependency.

## Current Mode

```text
EVERMIND_MEMORY_MODE=local
EVERMIND_SYNC_MODE=off
```

Local EverOS and Basic Memory remain the source of truth.

## Future Modes

- `local`: local-only memory.
- `local+backup`: local source of truth with manual cloud backup.
- `local+sync`: local-first with cloud synchronization.
- `cloud-primary+local-cache`: cloud source of truth with local cache.

## Reserved Environment Variables

```text
EVERMIND_MEMORY_MODE=local
EVERMIND_SYNC_MODE=off
EVERMIND_CLOUD_BASE_URL=
EVERMIND_CLOUD_API_KEY=
```

## Non-Goals For v1

- no hosted dashboard;
- no team permission system;
- no automatic cloud upload;
- no cloud-first default.

