"""Egress guard — in local mode, all outbound HTTP goes through one factory.

In local mode:
- Only localhost Ollama and configured targets are allowed
- HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1 are enforced
- LangSmith tracing is disabled
- Cloud clients cannot be created
"""

from __future__ import annotations

import os
import re
from typing import Any

from agentica.config.logging import get_logger

logger = get_logger(__name__)

_LOCALHOST_PATTERNS = [
    re.compile(r"^https?://localhost"),
    re.compile(r"^https?://127\.0\.0\.1"),
    re.compile(r"^https?://\[::1\]"),
]


def enforce_local_mode() -> None:
    """Set all required env vars for fully offline operation."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    logger.info("local_mode_enforced", hf_offline=1, transformers_offline=1)


def is_local_allowed(url: str, extra_hosts: set[str] | None = None) -> bool:
    """Return True if the URL is allowed in local mode (localhost or a configured target)."""
    if any(p.match(url) for p in _LOCALHOST_PATTERNS):
        return True
    if extra_hosts:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        return host in {h.lower() for h in extra_hosts}
    return False


def configured_target_hosts() -> set[str]:
    try:
        from agentica.tools.remote.target_manager import load_targets
        return {str(t["host"]) for t in load_targets() if t.get("host")}
    except Exception:
        return set()


def check_egress(url: str, mode: str = "local") -> None:
    """Raise RuntimeError if url violates local mode egress policy."""
    if mode != "local":
        return
    if not is_local_allowed(url, configured_target_hosts()):
        raise RuntimeError(
            f"Egress blocked in local mode: {url}. "
            "Only localhost connections (Ollama, configured targets) are allowed."
        )
