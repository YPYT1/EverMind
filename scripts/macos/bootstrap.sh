#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "EverMind bootstrap starts."
bash "$PROJECT_ROOT/scripts/macos/install-all.sh"
bash "$PROJECT_ROOT/scripts/macos/setup-user.sh"
bash "$PROJECT_ROOT/scripts/macos/check-all.sh"

