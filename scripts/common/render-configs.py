#!/usr/bin/env python3
"""Render local path defaults into an EverMind .env file."""

from __future__ import annotations

import argparse
from pathlib import Path


def replace_line(text: str, key: str, value: str) -> str:
    lines = text.splitlines()
    rendered = []
    found = False
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
            rendered.append(f"{key}={value}")
            found = True
        else:
            rendered.append(line)
    if not found:
        rendered.append(f"{key}={value}")
    return "\n".join(rendered) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--evermind-home", required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--archive-candidate-dir", required=True)
    args = parser.parse_args()

    path = Path(args.env_file)
    text = path.read_text(encoding="utf-8")
    replacements = {
        "EVERMIND_HOME": args.evermind_home,
        "EVERMIND_ARCHIVE_ROOT": args.archive_root,
        "EVERMIND_ARCHIVE_CANDIDATE_DIR": args.archive_candidate_dir,
    }
    for key, value in replacements.items():
        text = replace_line(text, key, value)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()


