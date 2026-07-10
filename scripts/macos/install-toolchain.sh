#!/usr/bin/env bash
set -euo pipefail

BEST_EFFORT=0
if [[ "${1:-}" == "--best-effort" ]]; then
  BEST_EFFORT=1
fi

info() { printf '[EverMind] %s\n' "$1"; }
pass() { printf '[OK] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }
stop_or_warn() {
  if [[ "$BEST_EFFORT" -eq 1 ]]; then
    warn "$1"
    return 0
  fi
  printf '[ERROR] %s\n' "$1" >&2
  exit 1
}

if ! xcode-select -p >/dev/null 2>&1; then
  info "Installing Xcode Command Line Tools"
  xcode-select --install || true
  stop_or_warn "Xcode Command Line Tools installation was started. Finish the macOS prompt, then rerun this script."
fi

if ! command -v brew >/dev/null 2>&1; then
  stop_or_warn "Homebrew is required to install optional build tools automatically. Install Homebrew or install llvm make cmake ninja manually."
else
  missing=()
  command -v llvm-config >/dev/null 2>&1 || command -v clang >/dev/null 2>&1 || missing+=("llvm")
  command -v make >/dev/null 2>&1 || missing+=("make")
  command -v cmake >/dev/null 2>&1 || missing+=("cmake")
  command -v ninja >/dev/null 2>&1 || missing+=("ninja")
  if [[ "${#missing[@]}" -gt 0 ]]; then
    info "Installing source-fusion build tools with Homebrew: ${missing[*]}"
    brew install "${missing[@]}"
  fi
fi

if ! command -v make >/dev/null 2>&1; then
  stop_or_warn "make is still missing"
elif ! command -v clang >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1 && ! command -v cc >/dev/null 2>&1; then
  stop_or_warn "clang/gcc/cc is still missing"
else
  pass "Source-fusion build toolchain is available"
fi
