"""Target manager — loads targets from targets.yaml, provides SSH and WinRM targets."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml

from agentica.config.secrets import SecretsManager
from agentica.config.logging import get_logger

logger = get_logger(__name__)

_TARGETS_PATH = Path(__file__).parents[4] / "config" / "defaults" / "targets.yaml"


def _load_target_config(target_id: str) -> dict | None:
    if not _TARGETS_PATH.exists():
        return None
    data = yaml.safe_load(_TARGETS_PATH.read_text(encoding="utf-8")) or {}
    for t in data.get("targets", []):
        if t.get("id") == target_id:
            return t
    return None


async def get_target(target_id: str):
    """Return an SSH or WinRM target object for the given target_id."""
    cfg = _load_target_config(target_id)
    if not cfg:
        raise ValueError(f"Target '{target_id}' not found in targets.yaml")

    if not (cfg.get("trusted_fingerprint") or cfg.get("trusted_thumbprint")):
        raise ValueError(
            f"Target '{target_id}' is not trusted. Use the Machines page to trust it first."
        )

    if cfg["type"] == "ssh":
        from agentica.tools.remote.ssh_target import SSHTarget
        user = SecretsManager.get(f"target_{target_id}_user") or cfg.get("user", "agentica")
        password = SecretsManager.get(f"target_{target_id}_password")
        key = SecretsManager.get(f"target_{target_id}_key")
        return SSHTarget(
            host=cfg["host"],
            port=cfg.get("port", 22),
            username=user,
            password=password,
            private_key=key,
            trusted_fingerprint=cfg.get("trusted_fingerprint"),
        )
    elif cfg["type"] == "winrm":
        from agentica.tools.remote.winrm_target import WinRMTarget
        user = SecretsManager.get(f"target_{target_id}_user") or cfg.get("user", "Administrator")
        password = SecretsManager.get(f"target_{target_id}_password") or ""
        return WinRMTarget(
            host=cfg["host"],
            port=cfg.get("port", 5986),
            username=user,
            password=password,
            trusted_thumbprint=cfg.get("trusted_thumbprint"),
        )
    else:
        raise ValueError(f"Unknown target type: {cfg['type']}")


async def test_target(target_id: str) -> tuple[bool, str]:
    try:
        target = await get_target(target_id)
        rc, out, err = await target.run_command(["echo", "ping"], timeout=10)
        return rc == 0, out.strip() or "OK"
    except Exception as e:
        return False, str(e)
