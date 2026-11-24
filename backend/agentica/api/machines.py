"""Machines API — register remote targets, credentials (keyring), trust, test."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentica.config.logging import get_logger
from agentica.config.secrets import SecretsManager
from agentica.tools.remote import target_manager as tm

router = APIRouter()
logger = get_logger(__name__)


class AddMachineRequest(BaseModel):
    id: str = Field(..., pattern=tm.TARGET_ID_PATTERN)
    type: Literal["ssh", "winrm"]
    host: str = Field(..., min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.\-:\[\]]+$")
    port: int | None = Field(default=None, ge=1, le=65535)
    user: str | None = Field(default=None, max_length=64)
    model_config = {"extra": "forbid"}


class SetCredentialsRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    private_key: str | None = None
    model_config = {"extra": "forbid"}


class TrustRequest(BaseModel):
    fingerprint: str | None = None  # SSH: "SHA256:..." or MD5 "aa:bb:.."
    thumbprint: str | None = None   # WinRM: certificate SHA-1 thumbprint
    model_config = {"extra": "forbid"}


def _require(target_id: str) -> dict:
    cfg = tm._load_target_config(target_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Target not found")
    return cfg


@router.get("/machines")
async def list_machines() -> list[dict]:
    result = []
    for t in tm.load_targets():
        tid = t["id"]
        has_cred = SecretsManager.get(f"target_{tid}_password") is not None or \
            SecretsManager.get(f"target_{tid}_key") is not None
        result.append({
            "id": tid,
            "type": t.get("type"),
            "host": t.get("host"),
            "port": t.get("port"),
            "user": SecretsManager.get(f"target_{tid}_user") or t.get("user"),
            "trusted": bool(t.get("trusted_fingerprint") or t.get("trusted_thumbprint")),
            "trusted_value": t.get("trusted_fingerprint") or t.get("trusted_thumbprint"),
            "has_credentials": has_cred,
        })
    return result


@router.post("/machines")
async def add_machine(body: AddMachineRequest) -> dict:
    try:
        return tm.add_target(body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/machines/{target_id}")
async def delete_machine(target_id: str) -> dict:
    if not tm.remove_target(target_id):
        raise HTTPException(status_code=404, detail="Target not found")
    return {"ok": True}


@router.post("/machines/{target_id}/credentials")
async def set_credentials(target_id: str, body: SetCredentialsRequest) -> dict:
    _require(target_id)
    if body.password:
        SecretsManager.set(f"target_{target_id}_password", body.password)
    if body.private_key:
        SecretsManager.set(f"target_{target_id}_key", body.private_key)
    if body.username:
        SecretsManager.set(f"target_{target_id}_user", body.username)
    return {"ok": True}


@router.get("/machines/{target_id}/fingerprint")
async def fetch_fingerprint(target_id: str) -> dict:
    """Show what the server presents so the admin can compare it before trusting."""
    cfg = _require(target_id)
    loop = asyncio.get_running_loop()
    try:
        if cfg["type"] == "ssh":
            from agentica.tools.remote.ssh_target import fetch_host_fingerprint
            fp = await loop.run_in_executor(None, fetch_host_fingerprint, cfg["host"], int(cfg.get("port", 22)))
            return {"type": "ssh", "value": fp["sha256"], **fp}
        from agentica.tools.remote.winrm_target import fetch_cert_thumbprint
        tp = await loop.run_in_executor(None, fetch_cert_thumbprint, cfg["host"], int(cfg.get("port", 5986)))
        return {"type": "winrm", "value": tp["sha1"], **tp}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach {cfg['host']}:{cfg.get('port')}: {e}")


@router.post("/machines/{target_id}/trust")
async def trust_target(target_id: str, body: TrustRequest) -> dict:
    cfg = _require(target_id)
    value = body.fingerprint if cfg["type"] == "ssh" else (body.thumbprint or body.fingerprint)
    if not value or not value.strip():
        raise HTTPException(status_code=400, detail="A fingerprint/thumbprint is required")
    if cfg["type"] == "ssh":
        tm.set_trust(target_id, fingerprint=value)
    else:
        tm.set_trust(target_id, thumbprint=value)
    return {"ok": True}


@router.delete("/machines/{target_id}/trust")
async def untrust_target(target_id: str) -> dict:
    cfg = _require(target_id)
    if cfg["type"] == "ssh":
        tm.set_trust(target_id, fingerprint="")
    else:
        tm.set_trust(target_id, thumbprint="")
    return {"ok": True}


@router.post("/machines/{target_id}/test")
async def test_connection(target_id: str) -> dict:
    _require(target_id)
    ok, msg = await tm.test_target(target_id)
    return {"ok": ok, "message": msg}
