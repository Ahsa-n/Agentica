"""Windows remote collectors: PowerShell over WinRM, always via ConvertTo-Json.

Scripts are constants; the only interpolated values are model-supplied names, and
those always pass through ps_quote() (single-quoted literal, quotes doubled).
Parsers accept PowerShell's single-object-vs-array output shapes.
"""

from __future__ import annotations

import json
from typing import Any

from agentica.tools.base import BaseTarget
from agentica.tools.local.monitoring import (
    CPUResult, DiskPartition, DiskResult, MemoryResult, NetworkInterface,
    NetworkResult, ProcessInfo, ProcessListResult, SystemOverviewResult,
)
from agentica.tools.remote.winrm_target import ps_quote

_GB = 1e9

CPU_PS = (
    "$c = @(Get-CimInstance Win32_Processor); "
    "$p = @(Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor | Where-Object { $_.Name -ne '_Total' } "
    "| Sort-Object { [int]$_.Name }); "
    "[pscustomobject]@{ Load = ($c | Measure-Object -Property LoadPercentage -Average).Average; "
    "Cores = ($c | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum; "
    "PerCpu = @($p | ForEach-Object { [double]$_.PercentProcessorTime }) } | ConvertTo-Json -Compress"
)
MEMORY_PS = (
    "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory,"
    "TotalVirtualMemorySize,FreeVirtualMemory | ConvertTo-Json -Compress"
)
DISK_PS = (
    "@(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,VolumeName,FileSystem,Size,FreeSpace)"
    " | ConvertTo-Json -Compress"
)
NETWORK_PS = (
    "@(Get-NetAdapterStatistics | Select-Object Name,SentBytes,ReceivedBytes,SentUnicastPackets,"
    "ReceivedUnicastPackets,ReceivedPacketErrors,OutboundPacketErrors) | ConvertTo-Json -Compress"
)
PROCESSES_PS = (
    "$cores = (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors; "
    "$mem = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory; "
    "@(Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object { $_.Name -notin '_Total','Idle' } "
    "| ForEach-Object { [pscustomobject]@{ Id = $_.IDProcess; Name = $_.Name; "
    "Cpu = [math]::Round($_.PercentProcessorTime / $cores, 1); "
    "Mem = [math]::Round(100 * $_.WorkingSetPrivate / $mem, 2) } }) | ConvertTo-Json -Compress"
)
OVERVIEW_PS = (
    "$os = Get-CimInstance Win32_OperatingSystem; "
    "[pscustomobject]@{ Host = $env:COMPUTERNAME; OS = $os.Caption + ' ' + $os.Version; "
    "UptimeHours = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 1) } | ConvertTo-Json -Compress"
)
PORTS_PS = "@(Get-NetTCPConnection -State Listen | Select-Object -ExpandProperty LocalPort -Unique) | ConvertTo-Json -Compress"
PROCNAMES_PS = "@(Get-Process | Select-Object -ExpandProperty ProcessName) | ConvertTo-Json -Compress"
_STATUS_SEL = "Select-Object Name,DisplayName,@{n='Status';e={$_.Status.ToString()}}"
_SVC_ACTIONS = {"start": "Start-Service", "stop": "Stop-Service", "restart": "Restart-Service"}
_SVC_STATUS = {"Running": "active", "Stopped": "inactive", "StartPending": "active",
               "StopPending": "inactive", "Paused": "inactive"}


class RemoteCommandError(RuntimeError):
    pass


async def _ps_json(target: BaseTarget, script: str, timeout: int = 30) -> Any:
    rc, out, err = await target.run_ps(script, timeout=timeout)  # type: ignore[attr-defined]
    if rc != 0:
        raise RemoteCommandError(f"PowerShell failed on {getattr(target, 'host', 'target')} "
                                 f"(exit {rc}): {(err or out).strip()[:300]}")
    out = out.strip()
    return json.loads(out) if out else None


def as_list(value: Any) -> list:
    """ConvertTo-Json emits a bare object for one item and an array for many."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


# ─── Parsers ─────────────────────────────────────────────────────────────────

def parse_cpu(data: dict) -> CPUResult:
    per = [round(float(x), 1) for x in as_list(data.get("PerCpu"))]
    return CPUResult(
        percent=round(float(data.get("Load") or 0), 1),
        per_cpu=per,
        load_avg=[0.0, 0.0, 0.0],  # Windows has no load average
        core_count=int(data.get("Cores") or len(per)),
    )


def parse_memory(data: dict) -> MemoryResult:
    kb = lambda k: float(data.get(k) or 0)  # noqa: E731  (CIM reports KB)
    total, free = kb("TotalVisibleMemorySize"), kb("FreePhysicalMemory")
    vtotal, vfree = kb("TotalVirtualMemorySize"), kb("FreeVirtualMemory")
    swap_total = max(vtotal - total, 0)
    swap_used = max((vtotal - vfree) - (total - free), 0)
    to_gb = lambda k: round(k * 1024 / _GB, 2)  # noqa: E731
    return MemoryResult(
        total_gb=to_gb(total), used_gb=to_gb(total - free), available_gb=to_gb(free),
        percent=round(100 * (total - free) / total, 1) if total else 0.0,
        swap_total_gb=to_gb(swap_total), swap_used_gb=to_gb(min(swap_used, swap_total)),
    )


def parse_disk(data: Any) -> DiskResult:
    parts = []
    for d in as_list(data):
        size, free = float(d.get("Size") or 0), float(d.get("FreeSpace") or 0)
        parts.append(DiskPartition(
            mountpoint=d.get("DeviceID", ""), device=d.get("VolumeName") or d.get("DeviceID", ""),
            fstype=d.get("FileSystem") or "", total_gb=round(size / _GB, 2),
            used_gb=round((size - free) / _GB, 2), free_gb=round(free / _GB, 2),
            percent=round(100 * (size - free) / size, 1) if size else 0.0,
        ))
    return DiskResult(partitions=parts)


def parse_network(data: Any) -> NetworkResult:
    return NetworkResult(interfaces=[
        NetworkInterface(
            name=n.get("Name", ""), bytes_sent_mb=round(float(n.get("SentBytes") or 0) / 1e6, 2),
            bytes_recv_mb=round(float(n.get("ReceivedBytes") or 0) / 1e6, 2),
            packets_sent=int(n.get("SentUnicastPackets") or 0), packets_recv=int(n.get("ReceivedUnicastPackets") or 0),
            errin=int(n.get("ReceivedPacketErrors") or 0), errout=int(n.get("OutboundPacketErrors") or 0),
        ) for n in as_list(data)
    ])


def parse_processes(data: Any) -> list[ProcessInfo]:
    return [
        ProcessInfo(pid=int(p.get("Id") or 0), name=str(p.get("Name", "")), cpu_percent=float(p.get("Cpu") or 0),
                    memory_percent=float(p.get("Mem") or 0), status="running")
        for p in as_list(data)
    ]


def service_state(status: str | None) -> str:
    return _SVC_STATUS.get(status or "", "unknown")


# ─── Collectors ──────────────────────────────────────────────────────────────

async def cpu(target: BaseTarget) -> CPUResult:
    return parse_cpu(await _ps_json(target, CPU_PS))


async def memory(target: BaseTarget) -> MemoryResult:
    return parse_memory(await _ps_json(target, MEMORY_PS))


async def disk(target: BaseTarget) -> DiskResult:
    return parse_disk(await _ps_json(target, DISK_PS))


async def network(target: BaseTarget) -> NetworkResult:
    return parse_network(await _ps_json(target, NETWORK_PS))


async def top_processes(target: BaseTarget, limit: int, sort_by: str) -> ProcessListResult:
    procs = parse_processes(await _ps_json(target, PROCESSES_PS, timeout=60))
    key = "memory_percent" if sort_by == "memory" else "cpu_percent"
    procs.sort(key=lambda p: getattr(p, key), reverse=True)
    return ProcessListResult(processes=procs[:limit])


async def process_details(target: BaseTarget, pid: int) -> ProcessInfo:
    for p in parse_processes(await _ps_json(target, PROCESSES_PS, timeout=60)):
        if p.pid == int(pid):
            return p
    return ProcessInfo(pid=pid, name="<not found>", cpu_percent=0.0, memory_percent=0.0, status="not found")


async def overview(target: BaseTarget) -> SystemOverviewResult:
    o = await _ps_json(target, OVERVIEW_PS)
    return SystemOverviewResult(
        hostname=o.get("Host", ""), platform=o.get("OS", "Windows"),
        uptime_hours=float(o.get("UptimeHours") or 0),
        cpu=await cpu(target), memory=await memory(target), disk=await disk(target),
    )


async def service_status(target: BaseTarget, name: str) -> tuple[str, str | None, int | None]:
    script = f"Get-Service -Name {ps_quote(name)} -ErrorAction Stop | {_STATUS_SEL} | ConvertTo-Json -Compress"
    rc, out, err = await target.run_ps(script)  # type: ignore[attr-defined]
    if rc != 0 or not out.strip():
        return "unknown", f"Service '{name}' not found", None
    data = as_list(json.loads(out))[0]
    return service_state(data.get("Status")), data.get("DisplayName"), None


async def list_services(target: BaseTarget, state_filter: str) -> list[tuple[str, str]]:
    rows = [(s.get("Name", ""), service_state(s.get("Status")))
            for s in as_list(await _ps_json(target, f"@(Get-Service | {_STATUS_SEL}) | ConvertTo-Json -Compress"))]
    if state_filter in ("active", "inactive", "failed"):
        rows = [r for r in rows if r[1] == state_filter]
    return rows[:200]


async def service_action(target: BaseTarget, name: str, action: str) -> tuple[bool, str]:
    verb = _SVC_ACTIONS.get(action)
    if not verb:
        raise ValueError(f"unsupported action {action!r}")
    rc, out, err = await target.run_ps(f"{verb} -Name {ps_quote(name)} -ErrorAction Stop", timeout=60)  # type: ignore[attr-defined]
    return rc == 0, ("OK" if rc == 0 else (err or out).strip()[:300])


async def logs(target: BaseTarget, log_name: str, lines: int) -> list[str]:
    script = (
        f"@(Get-WinEvent -LogName {ps_quote(log_name)} -MaxEvents {int(lines)} | Select-Object "
        "@{n='Time';e={$_.TimeCreated.ToString('s')}},LevelDisplayName,ProviderName,Message) "
        "| ConvertTo-Json -Compress -Depth 2"
    )
    return [
        f"{e.get('Time', '')} [{e.get('LevelDisplayName', '')}] {e.get('ProviderName', '')}: "
        f"{str(e.get('Message') or '')[:200]}"
        for e in as_list(await _ps_json(target, script, timeout=60))
    ]


async def listening_ports(target: BaseTarget) -> list[int]:
    return sorted({int(p) for p in as_list(await _ps_json(target, PORTS_PS))})


async def process_names(target: BaseTarget) -> list[str]:
    return [str(n) for n in as_list(await _ps_json(target, PROCNAMES_PS))]
