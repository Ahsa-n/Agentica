"""Application health check tool — UP / DEGRADED / DOWN / UNKNOWN per configured app."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse, urlunparse

import psutil
import yaml
from pydantic import BaseModel, Field

from agentica.tools.base import BaseTarget, BaseTool, RiskTier, ToolCategory, ToolSpec
from agentica.tools.registry import registry
from agentica.tools.remote.collectors import backend_for, is_remote

_APPS_CONFIG = Path(__file__).parents[4] / "config" / "defaults" / "apps.yaml"


class AppCheck(BaseModel):
    check: Literal["process", "service", "port", "http"]
    ok: bool
    detail: str
    model_config = {"extra": "forbid"}


class AppHealthResult(BaseModel):
    id: str
    display_name: str
    status: Literal["UP", "DEGRADED", "DOWN", "UNKNOWN"]
    process_running: bool | None = None
    service_running: bool | None = None
    port_open: bool | None = None
    http_ok: bool | None = None
    checks: list[AppCheck] = Field(default_factory=list)
    model_config = {"extra": "forbid"}


class AppStatusResult(BaseModel):
    apps: list[AppHealthResult]
    note: str | None = None
    model_config = {"extra": "forbid"}


class AppStatusInput(BaseModel):
    app_id: str | None = Field(default=None, description="Check only this application id (omit for all)")
    model_config = {"extra": "forbid"}


# Kept for backwards compatibility with older imports.
EmptyInput = AppStatusInput


def _load_apps() -> list[dict]:
    if _APPS_CONFIG.exists():
        data = yaml.safe_load(_APPS_CONFIG.read_text(encoding="utf-8")) or {}
        return list(data.get("apps") or [])
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


async def _check_http(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    from agentica.config.egress_guard import check_egress
    from agentica.config.loader import get_settings
    try:
        check_egress(url, mode=get_settings().llm.mode)  # local mode: localhost + registered targets only
    except RuntimeError as e:
        return False, str(e)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            return resp.status_code < 500, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:160]


def _overall(results: list[bool]) -> str:
    if not results:
        return "UNKNOWN"
    if all(results):
        return "UP"
    if any(results):
        return "DEGRADED"
    return "DOWN"


class GetApplicationStatus(BaseTool[AppStatusInput, AppStatusResult]):
    spec = ToolSpec(
        name="get_application_status",
        description=(
            "Check the health of the configured applications (apps.yaml): process, service, "
            "TCP port and HTTP checks, each reported UP/DEGRADED/DOWN/UNKNOWN."
        ),
        category=ToolCategory.APPLICATIONS,
        risk_tier=RiskTier.READ,
        input_schema=AppStatusInput.model_json_schema(),
    )

    async def run(self, args: AppStatusInput, target: BaseTarget | None = None) -> AppStatusResult:
        apps = _load_apps()
        if args.app_id:
            apps = [a for a in apps if a.get("id") == args.app_id]
            if not apps:
                known = ", ".join(a.get("id", "?") for a in _load_apps()) or "none"
                return AppStatusResult(apps=[], note=f"No application '{args.app_id}' in apps.yaml (configured: {known})")
        if not apps:
            return AppStatusResult(apps=[], note="No applications are configured in config/defaults/apps.yaml")

        remote_ctx = await self._remote_context(target) if is_remote(target) else None
        return AppStatusResult(apps=[await self._check_app(app, target, remote_ctx) for app in apps])

    async def _remote_context(self, target: BaseTarget) -> dict:
        """Fetch process names and listening ports once per call, not once per app."""
        be = backend_for(target)
        return {"procs": await be.process_names(target), "ports": set(await be.listening_ports(target))}

    async def _check_app(self, app: dict, target: BaseTarget | None, rctx: dict | None) -> AppHealthResult:
        checks: list[AppCheck] = []
        fields: dict[str, bool | None] = {
            "process_running": None, "service_running": None, "port_open": None, "http_ok": None,
        }

        if app.get("process_name"):
            name = str(app["process_name"])
            if rctx is not None:
                ok = any(name.lower() in p.lower() for p in rctx["procs"])
            else:
                ok = _check_process(name)
            fields["process_running"] = ok
            checks.append(AppCheck(check="process", ok=ok, detail=f"process '{name}' {'running' if ok else 'not found'}"))

        if app.get("service_name"):
            from agentica.tools.local.services import service_status
            st = await service_status(str(app["service_name"]), target)
            ok = st.status == "active"
            fields["service_running"] = ok
            checks.append(AppCheck(check="service", ok=ok, detail=f"service '{st.name}' is {st.status}"))

        if app.get("tcp_port"):
            port = int(app["tcp_port"])
            ok = port in rctx["ports"] if rctx is not None else _check_port(port)
            fields["port_open"] = ok
            checks.append(AppCheck(check="port", ok=ok, detail=f"TCP {port} {'listening' if ok else 'closed'}"))

        if app.get("http_check"):
            url = str(app["http_check"])
            if target is not None and getattr(target, "host", None):
                # A localhost URL in apps.yaml means "on the machine being checked".
                parts = urlparse(url)
                if parts.hostname in ("localhost", "127.0.0.1"):
                    netloc = target.host + (f":{parts.port}" if parts.port else "")
                    url = urlunparse(parts._replace(netloc=netloc))
            ok, detail = await _check_http(url)
            fields["http_ok"] = ok
            checks.append(AppCheck(check="http", ok=ok, detail=f"GET {url} -> {detail}"))

        return AppHealthResult(
            id=app["id"],
            display_name=app.get("display_name", app["id"]),
            status=_overall([c.ok for c in checks]),
            checks=checks,
            **fields,
        )


registry.register(GetApplicationStatus())
