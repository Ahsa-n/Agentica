"""Application health check tool."""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import Literal

import psutil
import yaml
from pydantic import BaseModel

from agentica.tools.base import BaseTool, BaseTarget, RiskTier, ToolCategory, ToolSpec
from agentica.tools.registry import registry

_APPS_CONFIG = Path(__file__).parents[4] / "config" / "defaults" / "apps.yaml"


class AppHealthResult(BaseModel):
    id: str
    display_name: str
    status: Literal["UP", "DEGRADED", "DOWN", "UNKNOWN"]
    process_running: bool | None = None
    service_running: bool | None = None
    port_open: bool | None = None
    http_ok: bool | None = None
    model_config = {"extra": "forbid"}


class AppStatusResult(BaseModel):
    apps: list[AppHealthResult]
    model_config = {"extra": "forbid"}


class EmptyInput(BaseModel):
    model_config = {"extra": "forbid"}


def _load_apps() -> list[dict]:
    if _APPS_CONFIG.exists():
        data = yaml.safe_load(_APPS_CONFIG.read_text()) or {}
        return data.get("apps", [])
    return []


def _check_process(name: str) -> bool:
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and name.lower() in proc.info["name"].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def _check_port(port: int, host: str = "127.0.0.1", timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _check_http(url: str, timeout: float = 5.0) -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return resp.status_code < 500
    except Exception:
        return False


class GetApplicationStatus(BaseTool[EmptyInput, AppStatusResult]):
    spec = ToolSpec(
        name="get_application_status",
        description="Check the health of all monitored applications (UP/DEGRADED/DOWN).",
        category=ToolCategory.APPLICATIONS,
        risk_tier=RiskTier.READ,
        input_schema=EmptyInput.model_json_schema(),
    )

    async def run(self, args: EmptyInput, target: BaseTarget | None = None) -> AppStatusResult:
        apps = _load_apps()
        results = []
        for app in apps:
            result = await self._check_app(app)
            results.append(result)
        return AppStatusResult(apps=results)

    async def _check_app(self, app: dict) -> AppHealthResult:
        checks: dict[str, bool | None] = {
            "process_running": None,
            "service_running": None,
            "port_open": None,
            "http_ok": None,
        }

        if app.get("process_name"):
            checks["process_running"] = _check_process(app["process_name"])

        if app.get("tcp_port"):
            checks["port_open"] = _check_port(app["tcp_port"])

        if app.get("http_check"):
            checks["http_ok"] = await _check_http(app["http_check"])

        # Determine overall status
        active_checks = [v for v in checks.values() if v is not None]
        if not active_checks:
            status = "UNKNOWN"
        elif all(active_checks):
            status = "UP"
        elif any(active_checks):
            status = "DEGRADED"
        else:
            status = "DOWN"

        return AppHealthResult(
            id=app["id"],
            display_name=app.get("display_name", app["id"]),
            status=status,
            **checks,
        )


registry.register(GetApplicationStatus())
