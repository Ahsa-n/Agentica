"""Keyring wrapper + log/prompt redaction."""

from __future__ import annotations

import re

import keyring

_SERVICE = "agentica"

# Patterns redacted in logs and streamed events
_REDACT_PATTERNS = [
    re.compile(r"(?i)(password|secret|token|key|credential|private)['\"]?\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"[A-Za-z0-9+/]{32,}={0,2}"),  # bare base64 blobs ≥32 chars
]


class SecretsManager:
    """Read/write secrets via the OS keyring; never touch DB or config."""

    @staticmethod
    def set(key: str, value: str) -> None:
        keyring.set_password(_SERVICE, key, value)

    @staticmethod
    def get(key: str) -> str | None:
        return keyring.get_password(_SERVICE, key)

    @staticmethod
    def delete(key: str) -> None:
        try:
            keyring.delete_password(_SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass


def redact(text: str) -> str:
    """Replace secret-looking substrings with [REDACTED]."""
    for pat in _REDACT_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text
