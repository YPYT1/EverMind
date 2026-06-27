#!/usr/bin/env bash
set -euo pipefail

EVEROS_REPO="${EVEROS_REPO:-}"
EVEROS_ROOT="${EVEROS_ROOT:-$HOME/.evermind/everos}"
EVEROS_HOST="${EVEROS_HOST:-127.0.0.1}"
EVEROS_PORT="${EVEROS_PORT:-3378}"

if [[ -n "$EVEROS_REPO" ]]; then
  uv run --directory "$EVEROS_REPO" everos server start --host "$EVEROS_HOST" --port "$EVEROS_PORT" --root "$EVEROS_ROOT"
else
  everos server start --host "$EVEROS_HOST" --port "$EVEROS_PORT" --root "$EVEROS_ROOT"
fi

