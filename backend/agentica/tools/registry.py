"""Global tool registry — populated by importing tool modules."""

from __future__ import annotations

from .base import ToolRegistry

registry = ToolRegistry()


def _load_tools() -> None:
    """Import all tool modules so they self-register."""
    from agentica.tools.local import (  # noqa: F401
        apps,
        knowledge_tool,  # noqa: F401
        logs,
        monitoring,
        network,
        services,
    )


_load_tools()
