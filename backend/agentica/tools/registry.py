"""Global tool registry — populated by importing tool modules."""

from __future__ import annotations

from .base import ToolRegistry

registry = ToolRegistry()


def _load_tools() -> None:
    """Import all tool modules so they self-register."""
    from agentica.tools.local import monitoring, services, apps, network, logs  # noqa: F401
    from agentica.tools.local import knowledge_tool  # noqa: F401


_load_tools()
