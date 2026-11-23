"""Machines API — target management, credentials, trust."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentica.config.logging import get_logger
from agentica.config.secrets import SecretsManager

router = APIRouter()
logger = get_logger(__name__)

_TARGETS_PATH = Path(__file__).parents[3] / "config" / "defaults" / "targets.yaml"


def _load_targets() -> list[dict]:
    if _TARGETS_PATH.exists():
        data = yaml.safe_load(_TARGETS_PATH.read_text(encoding="utf-8")) or {}
        return data.get("targets", [])
    return []


def _save_targets(targets: list[dict]) -> None:
    _TARGETS_PATH.write_text(
        yaml.dump({"targets": targets}, default_flow_style=False),
        encoding="utf-8",
    )


class SetCredentialsRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    private_key: str | None = None


class TrustRequest(BaseModel):
    fingerprint: str | None = None  # SSH
    thumbprint: str | None = None   # WinRM


@router.get("/machines")
async def list_machines() -> list[dict]:
    targets = _load_targets()
    # Annotate with trust status (don't expose creds)
    result = []
    for t in targets:
        has_cred = SecretsManager.get(f"target_{t['id']}_password") is not None or \
                   SecretsManager.get(f"target_{t['id']}_key") is not None
        result.append({
            "id": t["id"],
            "type": t.get("type"),
            "host": t.get("host"),
            "port": t.get("port"),
            "user": t.get("user"),
            "trusted": bool(t.get("trusted_fingerprint") or t.get("trusted_thumbprint")),
            "has_credentials": has_cred,
        })
    return result


@router.post("/machines/{target_id}/credentials")
async def set_credentials(target_id: str, body: SetCredentialsRequest) -> dict:
    if body.password:
        SecretsManager.set(f"target_{target_id}_password", body.password)
    if body.private_key:
        SecretsManager.set(f"target_{target_id}_key", body.private_key)
    if body.username:
        SecretsManager.set(f"target_{target_id}_user", body.username)
    return {"ok": True}


@router.post("/machines/{target_id}/trust")
async def trust_target(target_id: str, body: TrustRequest) -> dict:
    targets = _load_targets()
    for t in targets:
        if t["id"] == target_id:
            if body.fingerprint:
                t["trusted_fingerprint"] = body.fingerprint
            if body.thumbprint:
                t["trusted_thumbprint"] = body.thumbprint
            _save_targets(targets)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Target not found")


@router.post("/machines/{target_id}/test")
async def test_connection(target_id: str) -> dict:
    from agentica.tools.remote.target_manager import get_target, test_target
    try:
        target = await get_target(target_id)
        ok, msg = await test_target(target_id)
        return {"ok": ok, "message": msg}
    except Exception as e:
        return {"ok": False, "message": str(e)}
