# Local To Cloud Roadmap

EverMind is local-first. Cloud memory is an optional future adapter, not a v1 dependency.

## Current Mode

```text
EVERMIND_MEMORY_MODE=local
EVERMIND_SYNC_MODE=off
```

In this mode:

- local runtime is the realtime memory source;
- EverMind Archive is the reviewed long-term knowledge base;
- code graph indexes are local;
- no cloud upload happens by default.

## Why Local First

Local-first memory gives users:

- control over project knowledge;
- readable Markdown archive files;
- predictable privacy boundaries;
- offline-friendly workflows;
- easier debugging.

It also avoids forcing a hosted account or dashboard into the first version.

## Future Modes

| Mode | Meaning |
| --- | --- |
| `local` | Local-only memory. Current default. |
| `local+backup` | Local source of truth with manual or scheduled encrypted cloud backup. |
| `local+sync` | Local-first with cloud synchronization across machines. |
| `cloud-primary+local-cache` | Cloud source of truth with a local cache. |

## Reserved Environment Variables

```text
EVERMIND_MEMORY_MODE=local
EVERMIND_SYNC_MODE=off
EVERMIND_CLOUD_BASE_URL=
EVERMIND_CLOUD_API_KEY=
```

These variables are present so future versions can add sync without changing the user-facing configuration shape.

## Non-Goals For v1

- no hosted dashboard;
- no team permission system;
- no automatic cloud upload;
- no cloud-first default;
- no silent remote persistence.

## Future Design Requirements

Any future cloud mode should preserve:

- explicit user consent;
- clear sync status;
- conflict handling;
- encrypted transport;
- safe secret filtering;
- ability to run local-only.

