"""Read-only host monitoring tools the LLM can call.

Each tool returns a small JSON-serialisable dict. main.py passes TOOLS to the model and
routes its tool calls through run_tool().
"""

import base64
import json
import platform
import shutil
import socket
import subprocess
import time
from collections import Counter
from datetime import datetime, timedelta

import psutil

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LEVELS = {"critical": "1", "error": "1,2", "warning": "1,2,3"}


def _gb(n):
    return round(n / 1024**3, 1)


def _num(s):
    try:
        return float(s)
    except ValueError:  # nvidia-smi reports "[N/A]" for unsupported fields
        return None


def _run(cmd, timeout=30):
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=timeout, creationflags=NO_WINDOW)
    if not out.stdout.strip():
        raise RuntimeError(out.stderr.strip() or f"{cmd[0]} produced no output")
    return out.stdout


def _powershell(script):
    # -EncodedCommand sidesteps Windows argv quoting, which mangles quotes inside -Command
    encoded = base64.b64encode(("[Console]::OutputEncoding = [Text.Encoding]::UTF8\n" + script).encode("utf-16-le"))
    return _run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded.decode()])


def _cpu_name():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    except (ImportError, OSError):
        return platform.processor()


def _sample(seconds=1.0):
    """Return (system CPU %, per-process-name stats). CPU % needs two readings: prime, wait, re-read.

    oneshot() matters on Windows: protected processes fall back to a slow system-wide query per
    attribute, so each pass over ~400 processes costs ~0.8s. That pass counts toward the wait.
    """
    start = time.monotonic()
    psutil.cpu_percent(None)
    procs = []
    for p in psutil.process_iter():
        try:
            with p.oneshot():
                procs.append((p, p.name()))
                p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(max(0.0, seconds - (time.monotonic() - start)))
    total = psutil.cpu_percent(None)
    threads = psutil.cpu_count() or 1

    groups = {}
    for p, name in procs:
        if p.pid == 0:  # "System Idle Process" reports idle time as usage
            continue
        try:
            with p.oneshot():
                cpu = p.cpu_percent(None) / threads  # psutil counts per core; divide to match Task Manager
                mem = p.memory_info().rss
        except psutil.Error:
            continue
        name = name or f"pid {p.pid}"
        g = groups.setdefault(name, {"name": name, "instances": 0, "cpu_percent": 0.0, "memory_mb": 0.0})
        g["instances"] += 1
        g["cpu_percent"] += cpu
        g["memory_mb"] += mem / 1024**2
    for g in groups.values():
        g["cpu_percent"] = round(g["cpu_percent"], 1)
        g["memory_mb"] = round(g["memory_mb"])
    return total, list(groups.values())


def _top(groups, key, n):
    return sorted(groups, key=lambda g: g[key], reverse=True)[:n]


def _disks():
    disks = []
    for part in psutil.disk_partitions():
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except OSError:  # empty card readers, BitLocker-locked drives
            continue
        # "C:" not "C:\": models echo the name inside **bold**, and "\*" is an escaped asterisk in Markdown
        disks.append({"drive": part.mountpoint.rstrip("\\"), "fs": part.fstype, "total_gb": _gb(u.total),
                      "free_gb": _gb(u.free), "percent_used": u.percent})
    return disks


def _gpus():
    if not shutil.which("nvidia-smi"):
        return []
    fields = "name,utilization.gpu,memory.used,memory.total,temperature.gpu"
    out = _run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"], timeout=10)
    gpus = []
    for line in out.strip().splitlines():
        name, util, used, total, temp = (x.strip() for x in line.rsplit(",", 4))
        used, total = _num(used), _num(total)
        gpus.append({"name": name, "usage_percent": _num(util),
                     "vram_used_gb": used and round(used / 1024, 1),
                     "vram_total_gb": total and round(total / 1024, 1),
                     "temperature_c": _num(temp)})
    return gpus


def system_overview():
    cpu, procs = _sample()
    vm, swap = psutil.virtual_memory(), psutil.swap_memory()
    now = datetime.now().replace(microsecond=0)
    boot = datetime.fromtimestamp(psutil.boot_time()).replace(microsecond=0)
    info = {
        "now": now.isoformat(),
        "host": socket.gethostname(),
        "os": platform.platform(),
        "boot_time": boot.isoformat(),
        "uptime": str(now - boot),
        "cpu": {"model": _cpu_name(), "cores": psutil.cpu_count(logical=False),
                "threads": psutil.cpu_count(), "usage_percent": cpu},
        "memory": {"total_gb": _gb(vm.total), "used_gb": _gb(vm.used),
                   "available_gb": _gb(vm.available), "percent": vm.percent},
        "page_file": {"total_gb": _gb(swap.total), "used_gb": _gb(swap.used), "percent": swap.percent},
        "disks": _disks(),
        "top_cpu": _top(procs, "cpu_percent", 3),
        "top_memory": _top(procs, "memory_mb", 3),
    }
    if gpus := _gpus():
        info["gpus"] = gpus
    if (bat := psutil.sensors_battery()) is not None:
        info["battery"] = {"percent": bat.percent, "plugged_in": bat.power_plugged}
    return info


def top_processes(sort_by="cpu", limit=10, name_contains=""):
    key = "memory_mb" if sort_by == "memory" else "cpu_percent"
    _, procs = _sample()
    if name_contains:
        procs = [g for g in procs if name_contains.lower() in g["name"].lower()]
    return {"sorted_by": key, "processes": _top(procs, key, max(1, min(int(limit), 30)))}


# Variables ($log, $levels, $hours, $limit) are prepended by event_log() from validated values.
_EVENT_SCRIPT = """
$ev = @(Get-WinEvent -FilterHashtable @{LogName=$log; Level=$levels; StartTime=(Get-Date).AddHours(-$hours)} -MaxEvents 1000 -ErrorAction SilentlyContinue)
$sorted = $ev | Group-Object ProviderName, Id |
    Sort-Object @{e='Count'; Descending=$true}, @{e={$_.Group[0].TimeCreated}; Descending=$true} |
    Select-Object -First $limit
$groups = foreach ($g in $sorted) {
    $new = $g.Group[0]; $old = $g.Group[-1]
    [pscustomobject]@{source=$new.ProviderName; event_id=$new.Id; level=$new.LevelDisplayName; count=$g.Count;
        first_seen=$old.TimeCreated.ToString('s'); last_seen=$new.TimeCreated.ToString('s'); message=$new.Message}
}
ConvertTo-Json -Compress -Depth 4 -InputObject @{total=$ev.Count; groups=@($groups)}
"""


def event_log(log="System", level="error", hours=24, limit=10):
    if log not in ("System", "Application"):
        raise ValueError("log must be 'System' or 'Application'")
    if level not in LEVELS:
        raise ValueError(f"level must be one of {list(LEVELS)}")
    hours = max(1, min(int(hours), 24 * 30))
    limit = max(1, min(int(limit), 25))
    data = json.loads(_powershell(f"$log='{log}'; $levels={LEVELS[level]}; $hours={hours}; $limit={limit}" + _EVENT_SCRIPT))
    for g in data["groups"]:
        g["message"] = " ".join((g["message"] or "").split())[:300]
    result = {"log": log, "level": level,
              "since": (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds"),
              "total_events": data["total"], "groups": data["groups"]}
    if data["total"] >= 1000:
        result["note"] = "Only the 1000 most recent events were examined."
    return result


def network_info():
    before = psutil.net_io_counters(pernic=True)
    time.sleep(1)
    after = psutil.net_io_counters(pernic=True)
    addrs = psutil.net_if_addrs()

    interfaces = []
    for name, st in psutil.net_if_stats().items():
        ipv4 = [a.address for a in addrs.get(name, []) if a.family == socket.AF_INET]
        if not st.isup or not ipv4 or ipv4 == ["127.0.0.1"]:
            continue
        iface = {"name": name, "ipv4": ipv4, "link_mbps": st.speed or None}
        if (b := before.get(name)) and (a := after.get(name)):
            iface |= {"download_mbps": round((a.bytes_recv - b.bytes_recv) * 8 / 1e6, 2),
                      "upload_mbps": round((a.bytes_sent - b.bytes_sent) * 8 / 1e6, 2),
                      "received_gb_since_boot": _gb(a.bytes_recv), "sent_gb_since_boot": _gb(a.bytes_sent)}
        interfaces.append(iface)

    names = {}

    def pname(pid):
        if not pid:
            return "System"
        if pid not in names:
            try:
                names[pid] = psutil.Process(pid).name()
            except psutil.Error:
                names[pid] = f"pid {pid}"
        return names[pid]

    conns = psutil.net_connections("inet")
    established = [c for c in conns if c.status == psutil.CONN_ESTABLISHED]
    listening = sorted({(c.laddr.port, pname(c.pid)) for c in conns if c.status == psutil.CONN_LISTEN})
    return {"interfaces": interfaces,
            "established_connections": len(established),
            "connections_by_process": dict(Counter(pname(c.pid) for c in established).most_common(8)),
            "listening_ports": [{"port": port, "process": proc} for port, proc in listening][:40]}


def services(name_contains=""):
    found = []
    for s in psutil.win_service_iter():
        try:
            d = s.as_dict()
        except psutil.Error:
            continue
        if name_contains:
            if name_contains.lower() not in f"{d['name']} {d['display_name']}".lower():
                continue
        elif not (d["start_type"] == "automatic" and d["status"] != "running"):
            continue
        found.append({k: d[k] for k in ("name", "display_name", "status", "start_type")})
    return {"count": len(found), "services": found[:40]}


FUNCTIONS = {f.__name__: f for f in (system_overview, top_processes, event_log, network_info, services)}


def _tool(name, description, properties=None):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": []}}}


# Written by hand rather than generated from the functions: ollama's converter drops enums and
# marks every argument required, which trips up smaller local models.
TOOLS = [
    _tool("system_overview",
          "Snapshot of this PC: OS, uptime, CPU usage, RAM, page file, every disk's free space, GPU usage/VRAM/"
          "temperature, battery, and the top 3 processes by CPU and by memory. Use only when the user asks "
          "about this computer's health or performance, e.g. 'how is my PC doing' or 'why is it slow'."),
    _tool("top_processes",
          "Running processes grouped by name (instances summed) with CPU % and memory MB, sampled over 1 second. "
          "Use to find what is using CPU or RAM, or to check whether a specific program is running.",
          {"sort_by": {"type": "string", "enum": ["cpu", "memory"], "description": "Sort order. Default cpu."},
           "limit": {"type": "integer", "description": "How many to return, 1-30. Default 10."},
           "name_contains": {"type": "string", "description": "Only processes whose name contains this text, e.g. 'chrome'."}}),
    _tool("event_log",
          "Recent Windows Event Log entries, grouped by source and event ID with a count, first/last seen time and "
          "a sample message. Use for crashes, unexpected shutdowns, driver, disk or update errors.",
          {"log": {"type": "string", "enum": ["System", "Application"],
                   "description": "System = OS, drivers, hardware, shutdowns. Application = app crashes and errors. Default System."},
           "level": {"type": "string", "enum": ["critical", "error", "warning"],
                     "description": "Minimum severity; each level includes the ones above it. Default error."},
           "hours": {"type": "integer", "description": "How far back to look, 1-720. Default 24."},
           "limit": {"type": "integer", "description": "Maximum groups to return, 1-25. Default 10."}}),
    _tool("network_info",
          "Active network adapters with IPs, link speed and current download/upload rate, established connection "
          "count by process, and listening ports with their owning process."),
    _tool("services",
          "Windows services. Without name_contains, lists automatic-start services that are not running (updater "
          "services such as edgeupdate are often stopped by design). With name_contains, returns matching "
          "services in any state.",
          {"name_contains": {"type": "string", "description": "Filter by service name or display name, e.g. 'spooler'."}}),
]


def run_tool(name, args):
    fn = FUNCTIONS.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool '{name}'."})
    try:
        return json.dumps(fn(**(args or {})), default=str, separators=(",", ":"))
    except Exception as e:  # hand the failure back to the model so it can explain or retry
        return json.dumps({"error": f"{type(e).__name__}: {e}"})
