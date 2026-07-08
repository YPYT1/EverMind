"""Sensitive content detection for memory writes."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SensitiveMatch:
    category: str
    matched_text: str
    description: str
    start: int
    end: int


_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "private_key",
        "Private key block",
        re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    ),
    (
        "connection_string",
        "Connection string containing inline credentials",
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb|redis)://[^:\s/@]+:[^@\s]+@[\w.-]+", re.I),
    ),
    (
        "api_key",
        "OpenAI-compatible API key",
        re.compile(r"\bsk-(?:proj-|ant-api03-)?[A-Za-z0-9_-]{24,}\b"),
    ),
    (
        "aws_key",
        "AWS access key ID",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "github_token",
        "GitHub token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    ),
    (
        "slack_token",
        "Slack token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    ),
    (
        "password",
        "Password assignment",
        re.compile(r"\bpassword\s*=\s*['\"]?[^'\"\s]{8,}", re.I),
    ),
    (
        "secret",
        "Secret or token assignment",
        re.compile(r"\b(?:api[_-]?key|secret|token)\s*=\s*['\"]?[A-Za-z0-9_./:+-]{16,}", re.I),
    ),
    (
        "bearer_token",
        "Bearer token",
        re.compile(r"\bBearer\s+[A-Za-z0-9_./:+-]{24,}\b", re.I),
    ),
)


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "****"
    prefix_len = 8 if value.startswith(("sk-proj-", "github_")) else 6
    return value[:prefix_len] + "****"


def scan_sensitive_content(text: str) -> list[SensitiveMatch]:
    """Return masked sensitive matches found in text."""
    raw: list[SensitiveMatch] = []
    for category, description, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            raw.append(
                SensitiveMatch(
                    category=category,
                    matched_text=_mask(match.group(0)),
                    description=description,
                    start=match.start(),
                    end=match.end(),
                )
            )

    raw.sort(key=lambda m: (m.start, -(m.end - m.start)))
    deduped: list[SensitiveMatch] = []
    for match in raw:
        if any(match.start >= existing.start and match.end <= existing.end for existing in deduped):
            continue
        deduped.append(match)
    return deduped
