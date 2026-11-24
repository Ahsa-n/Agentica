"""Pick the collector module for a target: Linux (SSH) or Windows (WinRM)."""

from __future__ import annotations

from types import ModuleType

from agentica.tools.base import BaseTarget


def is_remote(target: BaseTarget | None) -> bool:
    return target is not None and getattr(target, "os_family", "local") != "local"


def backend_for(target: BaseTarget) -> ModuleType:
    family = getattr(target, "os_family", "local")
    if family == "windows":
        from agentica.tools.remote import windows
        return windows
    if family == "linux":
        from agentica.tools.remote import linux
        return linux
    raise ValueError(f"No remote collector for os_family={family!r}")
