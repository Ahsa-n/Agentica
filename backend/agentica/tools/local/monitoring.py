"""Local system monitoring tools — psutil-based, read-only."""

from __future__ import annotations

import psutil
from pydantic import BaseModel, Field

from agentica.tools.base import (
    BaseTarget,
    BaseTool,
    RiskTier,
    ToolCategory,
    ToolSpec,
)
from agentica.tools.registry import registry
from agentica.tools.remote.collectors import backend_for, is_remote

# ─── Shared result models ────────────────────────────────────────────────────

class CPUResult(BaseModel):
    percent: float
    per_cpu: list[float]
    load_avg: list[float]
    core_count: int
    model_config = {"extra": "forbid"}


class MemoryResult(BaseModel):
    total_gb: float
    used_gb: float
    available_gb: float
    percent: float
    swap_total_gb: float
    swap_used_gb: float
    model_config = {"extra": "forbid"}


class DiskPartition(BaseModel):
    mountpoint: str
    device: str
    fstype: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float
    model_config = {"extra": "forbid"}


class DiskResult(BaseModel):
    partitions: list[DiskPartition]
    model_config = {"extra": "forbid"}


class NetworkInterface(BaseModel):
    name: str
    bytes_sent_mb: float
    bytes_recv_mb: float
    packets_sent: int
    packets_recv: int
    errin: int
    errout: int
    model_config = {"extra": "forbid"}


class NetworkResult(BaseModel):
    interfaces: list[NetworkInterface]
    model_config = {"extra": "forbid"}


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    status: str
    username: str | None = None
    model_config = {"extra": "forbid"}


class ProcessListResult(BaseModel):
    processes: list[ProcessInfo]
    model_config = {"extra": "forbid"}


class SystemOverviewResult(BaseModel):
    hostname: str
    platform: str
    uptime_hours: float
    cpu: CPUResult
    memory: MemoryResult
    disk: DiskResult
    model_config = {"extra": "forbid"}


# ─── Tool definitions ─────────────────────────────────────────────────────────

class EmptyInput(BaseModel):
    model_config = {"extra": "forbid"}


class PidInput(BaseModel):
    pid: int = Field(..., description="Process ID to inspect")
    model_config = {"extra": "forbid"}


class TopProcessesInput(BaseModel):
    limit: int = Field(default=10, ge=1, le=50, description="Number of top processes to return")
    sort_by: str = Field(default="cpu", description="Sort by: cpu | memory")
    model_config = {"extra": "forbid"}


# ─── get_system_overview ─────────────────────────────────────────────────────

class GetSystemOverview(BaseTool[EmptyInput, SystemOverviewResult]):
    spec = ToolSpec(
        name="get_system_overview",
        description="Get a full overview of the local system: hostname, uptime, CPU, memory and disk.",
        category=ToolCategory.MONITORING,
        risk_tier=RiskTier.READ,
        input_schema=EmptyInput.model_json_schema(),
    )

    async def run(self, args: EmptyInput, target: BaseTarget | None = None) -> SystemOverviewResult:
        if is_remote(target):
            return await backend_for(target).overview(target)
        import platform
        import time
        cpu_pct = psutil.cpu_percent(interval=0.5)
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        partitions = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append(DiskPartition(
                    mountpoint=part.mountpoint,
                    device=part.device,
                    fstype=part.fstype,
                    total_gb=round(usage.total / 1e9, 2),
                    used_gb=round(usage.used / 1e9, 2),
                    free_gb=round(usage.free / 1e9, 2),
                    percent=usage.percent,
                ))
            except PermissionError:
                continue

        boot = psutil.boot_time()
        uptime_hours = round((time.time() - boot) / 3600, 1)

        try:
            load = list(psutil.getloadavg())
        except AttributeError:
            load = [0.0, 0.0, 0.0]

        return SystemOverviewResult(
            hostname=platform.node(),
            platform=platform.platform(),
            uptime_hours=uptime_hours,
            cpu=CPUResult(
                percent=cpu_pct,
                per_cpu=psutil.cpu_percent(percpu=True),
                load_avg=load,
                core_count=psutil.cpu_count(logical=True),
            ),
            memory=MemoryResult(
                total_gb=round(vm.total / 1e9, 2),
                used_gb=round(vm.used / 1e9, 2),
                available_gb=round(vm.available / 1e9, 2),
                percent=vm.percent,
                swap_total_gb=round(swap.total / 1e9, 2),
                swap_used_gb=round(swap.used / 1e9, 2),
            ),
            disk=DiskResult(partitions=partitions),
        )


class GetCPUUsage(BaseTool[EmptyInput, CPUResult]):
    spec = ToolSpec(
        name="get_cpu_usage",
        description="Get current CPU utilisation (overall and per-core).",
        category=ToolCategory.MONITORING,
        risk_tier=RiskTier.READ,
        input_schema=EmptyInput.model_json_schema(),
    )

    async def run(self, args: EmptyInput, target: BaseTarget | None = None) -> CPUResult:
        if is_remote(target):
            return await backend_for(target).cpu(target)
        try:
            load = list(psutil.getloadavg())
        except AttributeError:
            load = [0.0, 0.0, 0.0]
        return CPUResult(
            percent=psutil.cpu_percent(interval=0.5),
            per_cpu=psutil.cpu_percent(percpu=True),
            load_avg=load,
            core_count=psutil.cpu_count(logical=True),
        )


class GetMemoryUsage(BaseTool[EmptyInput, MemoryResult]):
    spec = ToolSpec(
        name="get_memory_usage",
        description="Get current memory and swap usage.",
        category=ToolCategory.MONITORING,
        risk_tier=RiskTier.READ,
        input_schema=EmptyInput.model_json_schema(),
    )

    async def run(self, args: EmptyInput, target: BaseTarget | None = None) -> MemoryResult:
        if is_remote(target):
            return await backend_for(target).memory(target)
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        return MemoryResult(
            total_gb=round(vm.total / 1e9, 2),
            used_gb=round(vm.used / 1e9, 2),
            available_gb=round(vm.available / 1e9, 2),
            percent=vm.percent,
            swap_total_gb=round(sw.total / 1e9, 2),
            swap_used_gb=round(sw.used / 1e9, 2),
        )


class GetDiskUsage(BaseTool[EmptyInput, DiskResult]):
    spec = ToolSpec(
        name="get_disk_usage",
        description="Get disk usage for all mounted partitions.",
        category=ToolCategory.MONITORING,
        risk_tier=RiskTier.READ,
        input_schema=EmptyInput.model_json_schema(),
    )

    async def run(self, args: EmptyInput, target: BaseTarget | None = None) -> DiskResult:
        if is_remote(target):
            return await backend_for(target).disk(target)
        partitions = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append(DiskPartition(
                    mountpoint=part.mountpoint,
                    device=part.device,
                    fstype=part.fstype,
                    total_gb=round(usage.total / 1e9, 2),
                    used_gb=round(usage.used / 1e9, 2),
                    free_gb=round(usage.free / 1e9, 2),
                    percent=usage.percent,
                ))
            except PermissionError:
                continue
        return DiskResult(partitions=partitions)


class GetNetworkStats(BaseTool[EmptyInput, NetworkResult]):
    spec = ToolSpec(
        name="get_network_stats",
        description="Get network interface I/O statistics.",
        category=ToolCategory.MONITORING,
        risk_tier=RiskTier.READ,
        input_schema=EmptyInput.model_json_schema(),
    )

    async def run(self, args: EmptyInput, target: BaseTarget | None = None) -> NetworkResult:
        if is_remote(target):
            return await backend_for(target).network(target)
        counters = psutil.net_io_counters(pernic=True)
        ifaces = []
        for name, c in counters.items():
            ifaces.append(NetworkInterface(
                name=name,
                bytes_sent_mb=round(c.bytes_sent / 1e6, 2),
                bytes_recv_mb=round(c.bytes_recv / 1e6, 2),
                packets_sent=c.packets_sent,
                packets_recv=c.packets_recv,
                errin=c.errin,
                errout=c.errout,
            ))
        return NetworkResult(interfaces=ifaces)


class ListTopProcesses(BaseTool[TopProcessesInput, ProcessListResult]):
    spec = ToolSpec(
        name="list_top_processes",
        description="List the top N processes sorted by CPU or memory usage.",
        category=ToolCategory.MONITORING,
        risk_tier=RiskTier.READ,
        input_schema=TopProcessesInput.model_json_schema(),
    )

    async def run(self, args: TopProcessesInput, target: BaseTarget | None = None) -> ProcessListResult:
        if is_remote(target):
            return await backend_for(target).top_processes(target, args.limit, args.sort_by)
        import asyncio
        # psutil's per-process cpu_percent is 0.0 on the first call; prime every process,
        # wait one sampling interval, then read real values.
        plist = list(psutil.process_iter())
        for p in plist:
            try:
                p.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        await asyncio.sleep(0.5)
        ncpu = psutil.cpu_count(logical=True) or 1
        procs = []
        for proc in plist:
            try:
                with proc.oneshot():
                    info = {
                        "pid": proc.pid, "name": proc.name(), "cpu_percent": proc.cpu_percent(None) / ncpu,
                        "memory_percent": proc.memory_percent(), "status": proc.status(),
                    }
                    try:
                        info["username"] = proc.username()
                    except psutil.AccessDenied:
                        info["username"] = None
                procs.append(ProcessInfo(
                    pid=info["pid"],
                    name=info["name"] or "",
                    cpu_percent=round(info["cpu_percent"] or 0.0, 1),
                    memory_percent=round(info["memory_percent"] or 0.0, 2),
                    status=info["status"] or "",
                    username=info.get("username"),
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        key = "cpu_percent" if args.sort_by == "cpu" else "memory_percent"
        procs.sort(key=lambda p: getattr(p, key), reverse=True)
        return ProcessListResult(processes=procs[: args.limit])


class GetProcessDetails(BaseTool[PidInput, ProcessInfo]):
    spec = ToolSpec(
        name="get_process_details",
        description="Get detailed information about a process by PID.",
        category=ToolCategory.MONITORING,
        risk_tier=RiskTier.READ,
        input_schema=PidInput.model_json_schema(),
    )

    async def run(self, args: PidInput, target: BaseTarget | None = None) -> ProcessInfo:
        if is_remote(target):
            return await backend_for(target).process_details(target, args.pid)
        try:
            proc = psutil.Process(args.pid)
            with proc.oneshot():
                return ProcessInfo(
                    pid=proc.pid,
                    name=proc.name(),
                    cpu_percent=proc.cpu_percent(interval=0.1),
                    memory_percent=round(proc.memory_percent(), 2),
                    status=proc.status(),
                    username=proc.username(),
                )
        except psutil.NoSuchProcess:
            return ProcessInfo(pid=args.pid, name="<not found>", cpu_percent=0.0,
                               memory_percent=0.0, status="not found")


# Register all tools
for _tool_cls in [
    GetSystemOverview, GetCPUUsage, GetMemoryUsage, GetDiskUsage,
    GetNetworkStats, ListTopProcesses, GetProcessDetails,
]:
    registry.register(_tool_cls())
