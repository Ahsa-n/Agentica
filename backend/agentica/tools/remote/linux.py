"""Linux remote collectors: run fixed argv on a target (SSH) and parse the output.

Parsers are pure functions over command output so they are unit-tested with
fixtures. Safety: model-supplied values (service names, units) are only ever
separate argv elements, which SSHTarget quotes with shlex. The few `sh -c`
scripts here are constants with no interpolated values.
"""

from __future__ import annotations

import re

from agentica.tools.base import BaseTarget
from agentica.tools.local.monitoring import (
    CPUResult, DiskPartition, DiskResult, MemoryResult, NetworkInterface,
    NetworkResult, ProcessInfo, ProcessListResult, SystemOverviewResult,
)

_SPLIT = "__AGENTICA_SPLIT__"

# Constant scripts (no interpolation) — two /proc/stat samples 0.5 s apart.
CPU_SCRIPT = f"cat /proc/stat; echo {_SPLIT}; sleep 0.5; cat /proc/stat; echo {_SPLIT}; cat /proc/loadavg"
OVERVIEW_SCRIPT = f"cat /proc/sys/kernel/hostname; echo {_SPLIT}; uname -sr; echo {_SPLIT}; cat /proc/uptime"

_PSEUDO_FS = {
    "tmpfs", "devtmpfs", "squashfs", "proc", "sysfs", "cgroup", "cgroup2", "devpts",
    "mqueue", "debugfs", "tracefs", "securityfs", "pstore", "autofs", "efivarfs", "shm",
    "fusectl", "configfs", "bpf", "hugetlbfs", "ramfs", "nsfs", "binfmt_misc",
}

_GB = 1e9


class RemoteCommandError(RuntimeError):
    pass


async def _run(target: BaseTarget, argv: list[str], timeout: int = 30, ok_codes=(0,)) -> str:
    rc, out, err = await target.run_command(argv, timeout=timeout)
    if rc not in ok_codes:
        raise RemoteCommandError(f"`{argv[0]}` failed on {getattr(target, 'host', 'target')} "
                                 f"(exit {rc}): {(err or out).strip()[:300]}")
    return out


def _priv(target: BaseTarget, argv: list[str]) -> list[str]:
    """Control actions use `sudo -n` (scoped sudoers from linux-target-setup.sh) unless root."""
    if getattr(target, "username", "root") == "root":
        return argv
    return ["sudo", "-n", *argv]


# ─── Parsers ─────────────────────────────────────────────────────────────────

def _cpu_times(block: str) -> dict[str, list[int]]:
    times: dict[str, list[int]] = {}
    for line in block.splitlines():
        if line.startswith("cpu"):
            parts = line.split()
            times[parts[0]] = [int(x) for x in parts[1:]]
    return times


def _busy_pct(a: list[int], b: list[int]) -> float:
    # fields: user nice system idle iowait irq softirq steal ...
    idle_a, idle_b = a[3] + (a[4] if len(a) > 4 else 0), b[3] + (b[4] if len(b) > 4 else 0)
    total = sum(b) - sum(a)
    if total <= 0:
        return 0.0
    return round(100.0 * (1 - (idle_b - idle_a) / total), 1)


def parse_cpu(text: str) -> CPUResult:
    parts = text.split(_SPLIT)
    if len(parts) < 3:
        raise ValueError("unexpected /proc/stat output")
    a, b = _cpu_times(parts[0]), _cpu_times(parts[1])
    cores = sorted((k for k in b if k != "cpu" and k in a), key=lambda k: int(k[3:]))
    load = [float(x) for x in parts[2].split()[:3]]
    return CPUResult(
        percent=_busy_pct(a["cpu"], b["cpu"]),
        per_cpu=[_busy_pct(a[k], b[k]) for k in cores],
        load_avg=load,
        core_count=len(cores),
    )


def parse_meminfo(text: str) -> MemoryResult:
    kb: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"^(\w+):\s+(\d+)", line)
        if m:
            kb[m.group(1)] = int(m.group(2))
    total = kb.get("MemTotal", 0)
    available = kb.get("MemAvailable", kb.get("MemFree", 0) + kb.get("Buffers", 0) + kb.get("Cached", 0))
    used = max(total - available, 0)
    swap_total = kb.get("SwapTotal", 0)
    swap_used = max(swap_total - kb.get("SwapFree", 0), 0)
    to_gb = lambda k: round(k * 1024 / _GB, 2)  # noqa: E731
    return MemoryResult(
        total_gb=to_gb(total),
        used_gb=to_gb(used),
        available_gb=to_gb(available),
        percent=round(100.0 * used / total, 1) if total else 0.0,
        swap_total_gb=to_gb(swap_total),
        swap_used_gb=to_gb(swap_used),
    )


def parse_df(text: str) -> DiskResult:
    """Parse `df -kPT`: Filesystem Type 1024-blocks Used Available Capacity Mounted-on."""
    parts_out: list[DiskPartition] = []
    for line in text.splitlines()[1:]:
        cols = line.split(None, 6)
        if len(cols) < 7:
            continue
        device, fstype, blocks, used, avail, cap, mount = cols
        if fstype in _PSEUDO_FS or not blocks.isdigit():
            continue
        parts_out.append(DiskPartition(
            mountpoint=mount,
            device=device,
            fstype=fstype,
            total_gb=round(int(blocks) * 1024 / _GB, 2),
            used_gb=round(int(used) * 1024 / _GB, 2),
            free_gb=round(int(avail) * 1024 / _GB, 2),
            percent=float(cap.rstrip("%") or 0),
        ))
    return DiskResult(partitions=parts_out)


def parse_net_dev(text: str) -> NetworkResult:
    ifaces: list[NetworkInterface] = []
    for line in text.splitlines()[2:]:
        if ":" not in line:
            continue
        name, data = line.split(":", 1)
        f = data.split()
        if len(f) < 16:
            continue
        ifaces.append(NetworkInterface(
            name=name.strip(),
            bytes_recv_mb=round(int(f[0]) / 1e6, 2),
            packets_recv=int(f[1]),
            errin=int(f[2]),
            bytes_sent_mb=round(int(f[8]) / 1e6, 2),
            packets_sent=int(f[9]),
            errout=int(f[10]),
        ))
    return NetworkResult(interfaces=ifaces)


def parse_ps(text: str) -> list[ProcessInfo]:
    """Parse `ps -eo pid=,user=,pcpu=,pmem=,stat=,comm=`."""
    procs: list[ProcessInfo] = []
    for line in text.splitlines():
        cols = line.split(None, 5)
        if len(cols) < 6 or not cols[0].isdigit():
            continue
        pid, user, pcpu, pmem, stat, comm = cols
        procs.append(ProcessInfo(
            pid=int(pid), name=comm.strip(), cpu_percent=float(pcpu),
            memory_percent=float(pmem), status=stat, username=user,
        ))
    return procs


def parse_systemctl_show(text: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    return props


def parse_proc_net_tcp(text: str) -> list[int]:
    """Listening TCP ports from /proc/net/tcp{,6} (state 0A = LISTEN)."""
    ports: set[int] = set()
    for line in text.splitlines():
        cols = line.split()
        if len(cols) < 4 or cols[0] == "sl" or ":" not in cols[1]:
            continue
        if cols[3] == "0A":
            ports.add(int(cols[1].rsplit(":", 1)[1], 16))
    return sorted(ports)


def parse_service_status_all(text: str) -> list[tuple[str, str]]:
    """Parse SysV `service --status-all` lines like ' [ + ]  nginx'."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*\[\s*([+\-?])\s*\]\s+(\S+)", line)
        if m:
            out.append((m.group(2), {"+": "active", "-": "inactive"}.get(m.group(1), "unknown")))
    return out


# ─── Collectors ──────────────────────────────────────────────────────────────

async def cpu(target: BaseTarget) -> CPUResult:
    return parse_cpu(await _run(target, ["sh", "-c", CPU_SCRIPT], timeout=15))


async def memory(target: BaseTarget) -> MemoryResult:
    return parse_meminfo(await _run(target, ["cat", "/proc/meminfo"]))


async def disk(target: BaseTarget) -> DiskResult:
    # df exits 1 if any mount is unreadable but still prints the rest.
    return parse_df(await _run(target, ["df", "-kPT"], ok_codes=(0, 1)))


async def network(target: BaseTarget) -> NetworkResult:
    return parse_net_dev(await _run(target, ["cat", "/proc/net/dev"]))


async def top_processes(target: BaseTarget, limit: int, sort_by: str) -> ProcessListResult:
    out = await _run(target, ["ps", "-eo", "pid=,user=,pcpu=,pmem=,stat=,comm="])
    procs = parse_ps(out)
    key = "memory_percent" if sort_by == "memory" else "cpu_percent"
    procs.sort(key=lambda p: getattr(p, key), reverse=True)
    return ProcessListResult(processes=procs[:limit])


async def process_details(target: BaseTarget, pid: int) -> ProcessInfo:
    rc, out, _ = await target.run_command(["ps", "-o", "pid=,user=,pcpu=,pmem=,stat=,comm=", "-p", str(int(pid))])
    procs = parse_ps(out) if rc == 0 else []
    if not procs:
        return ProcessInfo(pid=pid, name="<not found>", cpu_percent=0.0, memory_percent=0.0, status="not found")
    return procs[0]


async def overview(target: BaseTarget) -> SystemOverviewResult:
    host_out = await _run(target, ["sh", "-c", OVERVIEW_SCRIPT])
    hostname, platform, uptime = (p.strip() for p in host_out.split(_SPLIT)[:3])
    return SystemOverviewResult(
        hostname=hostname,
        platform=platform,
        uptime_hours=round(float(uptime.split()[0]) / 3600, 1),
        cpu=await cpu(target),
        memory=await memory(target),
        disk=await disk(target),
    )


def _no_systemd(rc: int, out: str, err: str) -> bool:
    text = (out + err).lower()
    return rc == 127 or "not been booted with systemd" in text or "command not found" in text \
        or "failed to connect to bus" in text


async def service_status(target: BaseTarget, name: str) -> tuple[str, str | None, int | None]:
    """Return (status, description, pid). Falls back to SysV `service` without systemd."""
    rc, out, err = await target.run_command(
        ["systemctl", "show", name, "--no-pager", "--property=ActiveState,LoadState,Description,MainPID"])
    if rc == 0 and "ActiveState=" in out:
        props = parse_systemctl_show(out)
        if props.get("LoadState") == "not-found":
            return "unknown", f"Service '{name}' not found", None
        state = props.get("ActiveState", "unknown")
        pid = props.get("MainPID", "0")
        return (state if state in ("active", "inactive", "failed") else "unknown",
                props.get("Description"), int(pid) if pid.isdigit() and pid != "0" else None)
    if not _no_systemd(rc, out, err):
        return "unknown", (err or out).strip()[:200] or None, None
    rc, out, err = await target.run_command(["service", name, "status"])
    text = (out + err).lower()
    if "unrecognized service" in text or "not found" in text:
        return "unknown", f"Service '{name}' not found", None
    return ("active" if rc == 0 else "inactive" if rc == 3 else "unknown"), None, None


async def list_services(target: BaseTarget, state_filter: str) -> list[tuple[str, str]]:
    argv = ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--no-legend", "--plain"]
    rc, out, err = await target.run_command(argv)
    if rc == 0 and not _no_systemd(rc, out, err):
        rows = []
        for line in out.splitlines():
            cols = line.split()
            if len(cols) >= 3:
                name = cols[0].removesuffix(".service")
                state = cols[2] if cols[2] in ("active", "inactive", "failed") else "unknown"
                rows.append((name, state))
    else:
        rows = parse_service_status_all(await _run(target, ["service", "--status-all"], ok_codes=(0, 1, 2, 3, 4)))
    if state_filter in ("active", "inactive", "failed"):
        rows = [r for r in rows if r[1] == state_filter]
    return rows[:200]


async def service_action(target: BaseTarget, name: str, action: str) -> tuple[bool, str]:
    if action not in ("start", "stop", "restart"):
        raise ValueError(f"unsupported action {action!r}")
    rc, out, err = await target.run_command(_priv(target, ["systemctl", action, name]), timeout=60)
    if _no_systemd(rc, out, err):
        rc, out, err = await target.run_command(_priv(target, ["service", name, action]), timeout=60)
    return rc == 0, ("OK" if rc == 0 else (err or out).strip()[:300])


async def logs(target: BaseTarget, unit: str, lines: int) -> list[str]:
    rc, out, err = await target.run_command(
        ["journalctl", "-u", unit, "--no-pager", "-n", str(int(lines)), "--output=short"], timeout=20)
    if rc != 0:
        raise RemoteCommandError((err or out).strip()[:300] or f"journalctl exited {rc}")
    return out.splitlines()[-lines:]


async def listening_ports(target: BaseTarget) -> list[int]:
    out = await _run(target, ["cat", "/proc/net/tcp", "/proc/net/tcp6"], ok_codes=(0, 1))
    return parse_proc_net_tcp(out)


async def process_names(target: BaseTarget) -> list[str]:
    out = await _run(target, ["ps", "-eo", "comm="])
    return [line.strip() for line in out.splitlines() if line.strip()]
