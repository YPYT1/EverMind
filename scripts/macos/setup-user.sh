#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
USER_HOME="${USER_HOME:-$HOME}"
COPY_INSTEAD_OF_SYMLINK="${COPY_INSTEAD_OF_SYMLINK:-0}"

info() { printf '[EverMind] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }

link_or_copy() {
  local source="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$dest" || -L "$dest" ]]; then
    info "Already exists: $dest"
    return
  fi
  if [[ "$COPY_INSTEAD_OF_SYMLINK" == "1" ]]; then
    cp -R "$source" "$dest"
    info "Copied: $dest"
  else
    ln -s "$source" "$dest"
    info "Linked: $dest -> $source"
  fi
}

SOURCE_SKILLS="$PROJECT_ROOT/skills"
AGENTS_SKILLS="$USER_HOME/.agents/skills"
mkdir -p "$AGENTS_SKILLS"

for skill in "$SOURCE_SKILLS"/*; do
  [[ -d "$skill" ]] || continue
  link_or_copy "$skill" "$AGENTS_SKILLS/$(basename "$skill")"
done

for client_home in "$USER_HOME/.codex" "$USER_HOME/.claude"; do
  if [[ ! -d "$client_home" ]]; then
    warn "Client directory not found, skipping: $client_home"
    continue
  fi
  mkdir -p "$client_home/skills"
  for skill in "$SOURCE_SKILLS"/*; do
    [[ -d "$skill" ]] || continue
    link_or_copy "$AGENTS_SKILLS/$(basename "$skill")" "$client_home/skills/$(basename "$skill")"
  done
done

info "User skills setup complete."

