"""Service management tools — read + modify/destructive. Local or remote target."""

from __future__ import annotations

import asyncio
import sys
from typing import Literal

from pydantic import BaseModel, Field

from agentica.tools.base import (
    BaseTool, BaseTarget, LocalTarget, RiskTier, ToolCategory, ToolResult, ToolSpec,
)
from agentica.tools.registry import registry
from agentica.tools.remote.collectors import backend_for, is_remote

# Service names: letters/digits first (so a name can never be read as an option like
# "--help"), then the characters systemd and the Windows SCM use in service names.
SERVICE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9@._:+\- ]{0,127}$"

VERIFY_ATTEMPTS = 6       # verify() polls for up to 30 s, per the spec
VERIFY_INTERVAL_S = 5


class ServiceStatusResult(BaseModel):
    name: str
    status: Literal["active", "inactive", "failed", "unknown"]
    description: str | None = None
    pid: int | None = None
    model_config = {"extra": "forbid"}


class ServiceListResult(BaseModel):
    services: list[ServiceStatusResult]
    model_config = {"extra": "forbid"}


class ServiceActionResult(BaseModel):
    name: str
    action: str
    success: bool
    message: str
    verified: bool | None = None
    model_config = {"extra": "forbid"}


class ServiceNameInput(BaseModel):
    name: str = Field(..., description="Service name, e.g. 'nginx' or 'Spooler'", pattern=SERVICE_NAME_PATTERN)
    model_config = {"extra": "forbid"}


class ListServicesInput(BaseModel):
    state_filter: Literal["all", "active", "inactive", "failed"] = Field(
        default="all", description="Filter: all | active | inactive | failed")
    model_config = {"extra": "forbid"}


def _is_windows() -> bool:
    return sys.platform == "win32"


async def _systemctl(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    target = LocalTarget()
    return await target.run_command(["systemctl"] + args, timeout=timeout)


async def _sc(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    target = LocalTarget()
    return await target.run_command(["sc"] + args, timeout=timeout)


async def _get_service_status_linux(name: str) -> ServiceStatusResult:
    rc, out, _ = await _systemctl(["show", name, "--property=ActiveState,Description,MainPID"])
    props: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    state = props.get("ActiveState", "unknown")
    status_map = {"active": "active", "inactive": "inactive", "failed": "failed"}
    pid_str = props.get("MainPID", "0")
    return ServiceStatusResult(
        name=name,
        status=status_map.get(state, "unknown"),
        description=props.get("Description"),
        pid=int(pid_str) if pid_str.isdigit() and pid_str != "0" else None,
    )


async def _get_service_status_windows(name: str) -> ServiceStatusResult:
    try:
        import win32service  # type: ignore
        scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        try:
            svc = win32service.OpenService(scm, name, win32service.SERVICE_QUERY_STATUS)
        except Exception:
            win32service.CloseServiceHandle(scm)
            return ServiceStatusResult(name=name, status="unknown", description=f"Service '{name}' not found")
        status = win32service.QueryServiceStatus(svc)
        win32service.CloseServiceHandle(svc)
        win32service.CloseServiceHandle(scm)
        state_map = {
            1: "inactive", 2: "active", 3: "active",
            4: "active", 5: "inactive", 6: "inactive", 7: "inactive",
        }
        return ServiceStatusResult(
            name=name,
            status=state_map.get(status[1], "unknown"),
        )
    except ImportError:
        rc, out, _ = await _sc(["query", name])
        if "RUNNING" in out:
            return ServiceStatusResult(name=name, status="active")
        elif "STOPPED" in out:
            return ServiceStatusResult(name=name, status="inactive")
        return ServiceStatusResult(name=name, status="unknown")


async def service_status(name: str, target: BaseTarget | None = None) -> ServiceStatusResult:
    """Status on the local machine or on a remote target."""
    if is_remote(target):
        status, desc, pid = await backend_for(target).service_status(target, name)
        return ServiceStatusResult(name=name, status=status, description=desc, pid=pid)
    if _is_windows():
        return await _get_service_status_windows(name)
    return await _get_service_status_linux(name)


class GetServiceStatus(BaseTool[ServiceNameInput, ServiceStatusResult]):
    spec = ToolSpec(
        name="get_service_status",
        description="Get the status of a system service by name.",
        category=ToolCategory.SERVICES,
        risk_tier=RiskTier.READ,
        input_schema=ServiceNameInput.model_json_schema(),
    )

    async def run(self, args: ServiceNameInput, target: BaseTarget | None = None) -> ServiceStatusResult:
        return await service_status(args.name, target)


class ListServices(BaseTool[ListServicesInput, ServiceListResult]):
    spec = ToolSpec(
        name="list_services",
        description="List system services, optionally filtered by state.",
        category=ToolCategory.SERVICES,
        risk_tier=RiskTier.READ,
        input_schema=ListServicesInput.model_json_schema(),
    )

    async def run(self, args: ListServicesInput, target: BaseTarget | None = None) -> ServiceListResult:
        if is_remote(target):
            rows = await backend_for(target).list_services(target, args.state_filter)
            return ServiceListResult(services=[ServiceStatusResult(name=n, status=s) for n, s in rows])
        if _is_windows():
            return await self._list_windows(args)
        return await self._list_linux(args)

    async def _list_linux(self, args: ListServicesInput) -> ServiceListResult:
        cmd = ["systemctl", "list-units", "--type=service", "--no-pager", "--no-legend"]
        if args.state_filter != "all":
            cmd += [f"--state={args.state_filter}"]
        rc, out, _ = await LocalTarget().run_command(cmd)
        services = []
        for line in out.splitlines()[:100]:
            parts = line.split()
            if not parts:
                continue
            name = parts[0].removesuffix(".service")
            state = parts[2] if len(parts) > 2 else "unknown"
            status_map = {"active": "active", "inactive": "inactive", "failed": "failed"}
            services.append(ServiceStatusResult(
                name=name,
                status=status_map.get(state, "unknown"),
            ))
        return ServiceListResult(services=services)

    async def _list_windows(self, args: ListServicesInput) -> ServiceListResult:
        rc, out, _ = await LocalTarget().run_command(
            ["sc", "query", "type=", "service", "state=", "all"]
        )
        services = []
        current_name = None
        for line in out.splitlines():
            if "SERVICE_NAME:" in line:
                current_name = line.split(":", 1)[1].strip()
            elif "STATE" in line and current_name:
                state = "active" if "RUNNING" in line else "inactive"
                services.append(ServiceStatusResult(name=current_name, status=state))
                current_name = None
        if args.state_filter in ("active", "inactive"):
            services = [s for s in services if s.status == args.state_filter]
        return ServiceListResult(services=services[:100])


async def _do_service_action(name: str, action: str, target: BaseTarget | None = None) -> ServiceActionResult:
    if is_remote(target):
        ok, msg = await backend_for(target).service_action(target, name, action)
        return ServiceActionResult(name=name, action=action, success=ok, message=msg)
    if _is_windows():
        try:
            import win32service, win32serviceutil  # type: ignore
            try:
                if action == "start":
                    win32serviceutil.StartService(name)
                elif action == "stop":
                    win32serviceutil.StopService(name)
                elif action == "restart":
                    win32serviceutil.RestartService(name)
            except Exception as e:  # pywintypes.error: not found, access denied, ...
                msg = e.args[2] if len(getattr(e, "args", ())) > 2 else str(e)
                return ServiceActionResult(name=name, action=action, success=False, message=str(msg))
            return ServiceActionResult(name=name, action=action, success=True, message="OK")
        except ImportError:
            sc_action = {"start": "start", "stop": "stop"}.get(action)
            if not sc_action:  # sc has no restart verb
                stop = await _do_service_action(name, "stop")
                if not stop.success:
                    return ServiceActionResult(name=name, action=action, success=False, message=stop.message)
                return (await _do_service_action(name, "start")).model_copy(update={"action": action})
            rc, out, err = await LocalTarget().run_command(["sc", sc_action, name])
            return ServiceActionResult(
                name=name, action=action,
                success=rc == 0,
                message=out or err,
            )
    else:
        rc, out, err = await LocalTarget().run_command(["systemctl", action, name])
        return ServiceActionResult(
            name=name, action=action,
            success=rc == 0,
            message=err if rc != 0 else "OK",
        )


async def _wait_for_status(name: str, wanted: str, target: BaseTarget | None) -> bool:
    for attempt in range(VERIFY_ATTEMPTS):
        st = await service_status(name, target)
        if st.status == wanted:
            return True
        if attempt < VERIFY_ATTEMPTS - 1:
            await asyncio.sleep(VERIFY_INTERVAL_S)
    return False


class StartService(BaseTool[ServiceNameInput, ServiceActionResult]):
    spec = ToolSpec(
        name="start_service",
        description="Start a system service. Requires confirmation.",
        category=ToolCategory.SERVICES,
        risk_tier=RiskTier.MODIFY,
        input_schema=ServiceNameInput.model_json_schema(),
    )

    async def run(self, args: ServiceNameInput, target: BaseTarget | None = None) -> ServiceActionResult:
        return await _do_service_action(args.name, "start", target)

    async def verify(self, args: ServiceNameInput, result: ServiceActionResult, target=None) -> bool:
        return await _wait_for_status(args.name, "active", target)


class RestartService(BaseTool[ServiceNameInput, ServiceActionResult]):
    spec = ToolSpec(
        name="restart_service",
        description="Restart a system service. Requires confirmation.",
        category=ToolCategory.SERVICES,
        risk_tier=RiskTier.MODIFY,
        input_schema=ServiceNameInput.model_json_schema(),
    )

    async def run(self, args: ServiceNameInput, target: BaseTarget | None = None) -> ServiceActionResult:
        return await _do_service_action(args.name, "restart", target)

    async def verify(self, args: ServiceNameInput, result: ServiceActionResult, target=None) -> bool:
        return await _wait_for_status(args.name, "active", target)


class StopService(BaseTool[ServiceNameInput, ServiceActionResult]):
    spec = ToolSpec(
        name="stop_service",
        description="Stop a system service. Destructive — requires confirmation.",
        category=ToolCategory.SERVICES,
        risk_tier=RiskTier.DESTRUCTIVE,
        input_schema=ServiceNameInput.model_json_schema(),
    )

    async def run(self, args: ServiceNameInput, target: BaseTarget | None = None) -> ServiceActionResult:
        return await _do_service_action(args.name, "stop", target)

    async def verify(self, args: ServiceNameInput, result: ServiceActionResult, target=None) -> bool:
        return await _wait_for_status(args.name, "inactive", target)


for _t in [GetServiceStatus, ListServices, StartService, RestartService, StopService]:
    registry.register(_t())
