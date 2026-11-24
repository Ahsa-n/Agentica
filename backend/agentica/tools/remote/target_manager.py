"""Target manager — targets.yaml registry, credentials from the keyring, target objects.

targets.yaml holds only non-secret connection details and the trusted host-key
fingerprint / certificate thumbprint. Passwords and private keys live in the OS
keyring (SecretsManager) and are never written to disk or returned by the API.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import yaml

from agentica.config.secrets import SecretsManager
from agentica.config.logging import get_logger

logger = get_logger(__name__)

_TARGETS_PATH = Path(__file__).parents[4] / "config" / "defaults" / "targets.yaml"
_LOCK = threading.Lock()

TARGET_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,62}$"
_HEADER = (
    "# Managed targets - edited via the Machines page or by hand.\n"
    "# Never contains secrets: passwords and keys live in the OS keyring.\n"
)


def load_targets() -> list[dict]:
    if not _TARGETS_PATH.exists():
        return []
    data = yaml.safe_load(_TARGETS_PATH.read_text(encoding="utf-8")) or {}
    return list(data.get("targets") or [])


def save_targets(targets: list[dict]) -> None:
    with _LOCK:
        body = yaml.safe_dump({"targets": targets}, default_flow_style=False, sort_keys=False)
        _TARGETS_PATH.write_text(_HEADER + body, encoding="utf-8")


def list_target_ids() -> list[str]:
    try:
        return [str(t["id"]) for t in load_targets() if t.get("id")]
    except Exception as e:  # a broken targets.yaml must not break chat
        logger.warning("targets_yaml_unreadable", error=str(e))
        return []


def _load_target_config(target_id: str) -> dict | None:
    for t in load_targets():
        if t.get("id") == target_id:
            return t
    return None


def add_target(cfg: dict) -> dict:
    if not re.match(TARGET_ID_PATTERN, cfg["id"]):
        raise ValueError("id must be lowercase letters, digits, '.', '_' or '-'")
    targets = load_targets()
    if any(t.get("id") == cfg["id"] for t in targets):
        raise ValueError(f"Target '{cfg['id']}' already exists")
    entry = {
        "id": cfg["id"],
        "type": cfg["type"],
        "host": cfg["host"],
        "port": int(cfg.get("port") or (22 if cfg["type"] == "ssh" else 5986)),
        "user": cfg.get("user") or ("agentica" if cfg["type"] == "ssh" else "Administrator"),
    }
    entry["trusted_fingerprint" if cfg["type"] == "ssh" else "trusted_thumbprint"] = None
    targets.append(entry)
    save_targets(targets)
    return entry


def remove_target(target_id: str) -> bool:
    targets = load_targets()
    kept = [t for t in targets if t.get("id") != target_id]
    if len(kept) == len(targets):
        return False
    save_targets(kept)
    for suffix in ("password", "key", "user"):
        SecretsManager.delete(f"target_{target_id}_{suffix}")
    return True


def set_trust(target_id: str, fingerprint: str | None = None, thumbprint: str | None = None) -> bool:
    targets = load_targets()
    for t in targets:
        if t.get("id") == target_id:
            if fingerprint is not None:
                t["trusted_fingerprint"] = fingerprint.strip() or None
            if thumbprint is not None:
                t["trusted_thumbprint"] = thumbprint.strip() or None
            save_targets(targets)
            return True
    return False


async def get_target(target_id: str):
    """Return an SSH or WinRM target object for the given target_id."""
    cfg = _load_target_config(target_id)
    if not cfg:
        known = ", ".join(list_target_ids()) or "none registered"
        raise ValueError(f"Target '{target_id}' not found (known targets: {known})")

    if not (cfg.get("trusted_fingerprint") or cfg.get("trusted_thumbprint")):
        raise ValueError(
            f"Target '{target_id}' is not trusted. Use the Machines page to trust it first."
        )

    if cfg["type"] == "ssh":
        from agentica.tools.remote.ssh_target import SSHTarget
        user = SecretsManager.get(f"target_{target_id}_user") or cfg.get("user", "agentica")
        password = SecretsManager.get(f"target_{target_id}_password")
        key = SecretsManager.get(f"target_{target_id}_key")
        if not (password or key):
            raise ValueError(f"No credentials stored for '{target_id}'. Set them on the Machines page.")
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
        if not password:
            raise ValueError(f"No credentials stored for '{target_id}'. Set them on the Machines page.")
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
        if target.os_family == "windows":
            rc, out, err = await target.run_ps(
                "[pscustomobject]@{ Host = $env:COMPUTERNAME; OS = (Get-CimInstance Win32_OperatingSystem).Caption }"
                " | ConvertTo-Json -Compress", timeout=20)
        else:
            rc, out, err = await target.run_command(["uname", "-snr"], timeout=15)
        if rc != 0:
            return False, (err or out).strip()[:300] or f"exit code {rc}"
        return True, f"Connected: {out.strip()[:200]}"
    except Exception as e:
        return False, str(e)
