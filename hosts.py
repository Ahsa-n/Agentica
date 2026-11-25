"""
Hosts — where a tool actually runs.

LocalHost  : this PC (psutil / pywin32 / systemctl)
SSHHost    : a registered Linux machine over SSH (paramiko, port 22). Each operation sends
             linux_remote.py to the target and runs it with python3 (nothing is installed).
WinRMHost  : a registered Windows machine over WinRM (pypsrp, HTTP 5985, NTLM with
             message encryption). Each operation is a FIXED PowerShell script; arguments
             are passed as PowerShell parameters, never pasted into script text. Every
             script returns JSON in the same shape as the local implementation, so the
             tools, the model and the UI do not care where a call ran.

HostRegistry resolves a target name (label, hostname, IP, "local") to a host.
Passwords come from the OS keyring; the database only stores the username.
"""
from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import tempfile
import threading
import time

from pathlib import Path

import keyring
import psutil

import appfind
import services
from telemetry import HOSTNAME, disks, os_label, sampler, uptime

KEYRING_SERVICE = "agentica"
# Dev/test only: AGENTICA_DEV=1 enables the "local-ps" transport, which runs the exact remote
# PowerShell scripts on this PC through powershell.exe. Lets the team exercise the whole remote
# pipeline (tools, approvals, fleet polling) without a second machine.
DEV = os.environ.get("AGENTICA_DEV") == "1"
LOCAL_NAMES = {"local", "localhost", "127.0.0.1", "::1", "this pc", "this-pc", HOSTNAME.lower()}


class RemoteError(Exception):
    """Connection / sign-in / remote execution problem; message is safe to show."""


class TargetError(str):
    """Why a target cannot be used. kind: 'request' (fix the name / add credentials) or 'state' (machine is down)."""
    kind = "request"

    @classmethod
    def state(cls, msg: str) -> "TargetError":
        e = cls(msg)
        e.kind = "state"
        return e


def _gb(n: float) -> float:
    return round(n / 1024**3, 2)


# =============================================================================== local

class LocalHost:
    is_local = True

    def __init__(self) -> None:
        self.label = HOSTNAME
        self.os = "windows" if services.IS_WINDOWS else "linux"
        self.names = {n for n in LOCAL_NAMES}

    def snapshot(self) -> dict:
        vm, sw, freq = psutil.virtual_memory(), psutil.swap_memory(), psutil.cpu_freq()
        with sampler.lock:
            cpu, cores = sampler.cpu, list(sampler.per_core)
            procs = sorted(sampler.procs, key=lambda p: p["cpu"], reverse=True)[:5]
        return {
            "host": HOSTNAME, "os": os_label(), "uptime_hours": round(uptime() / 3600, 1),
            "cpu": {"percent": cpu, "logical_cores": psutil.cpu_count(logical=True),
                    "physical_cores": psutil.cpu_count(logical=False),
                    "busiest_core_percent": max(cores) if cores else None,
                    "freq_mhz": round(freq.current) if freq else None},
            "memory": {"total_gb": _gb(vm.total), "used_gb": _gb(vm.total - vm.available),
                       "available_gb": _gb(vm.available), "percent": vm.percent},
            "swap": {"total_gb": _gb(sw.total), "percent": sw.percent},
            "top_cpu_processes": [{"name": p["name"], "pid": p["pid"], "cpu_percent": p["cpu"]} for p in procs],
        }

    def top_processes(self, sort_by: str, limit: int) -> dict:
        with sampler.lock:
            procs = list(sampler.procs)
        procs.sort(key=(lambda p: p["cpu"]) if sort_by == "cpu" else (lambda p: p["rss"]), reverse=True)
        total = psutil.virtual_memory().total
        return {"sorted_by": sort_by, "processes": [
            {"name": p["name"], "pid": p["pid"], "cpu_percent": p["cpu"], "memory_mb": round(p["rss"] / 1024**2, 1),
             "memory_percent": round(p["rss"] / total * 100, 2)} for p in procs[:limit]]}

    def disk_usage(self) -> dict:
        return {"volumes": [{"mount": d["mount"], "fstype": d["fstype"], "total_gb": _gb(d["total"]),
                             "used_gb": _gb(d["used"]), "free_gb": _gb(d["free"]), "percent_used": d["percent"]}
                            for d in disks()]}

    def network_info(self) -> dict:
        stats, addrs = psutil.net_if_stats(), psutil.net_if_addrs()
        ifaces = []
        for name, st in stats.items():
            v4 = [x.address for x in addrs.get(name, []) if x.family == socket.AF_INET]
            if st.isup or v4:
                ifaces.append({"name": name, "up": st.isup, "speed_mbps": st.speed, "ipv4": v4})
        with sampler.lock:
            rx, tx = sampler.rx_rate, sampler.tx_rate
        return {"hostname": HOSTNAME, "throughput": {"rx_kbps": round(rx * 8 / 1000, 1), "tx_kbps": round(tx * 8 / 1000, 1)},
                "interfaces": ifaces}

    def processes_named(self, names: list[str]) -> dict:
        """Running processes whose name matches one of `names` (case-insensitive, '.exe' optional), with
        totals (CPU %, memory), their windows and how many of those are not responding."""
        want = {n.lower().removesuffix(".exe") for n in names if n}
        with sampler.lock:
            cpu_by_pid = {p["pid"]: p["cpu"] for p in sampler.procs}
        wins = appfind.windows_by_pid()
        found = []
        for p in psutil.process_iter(["pid", "name", "memory_info", "create_time"]):
            try:
                n = (p.info["name"] or "").lower().removesuffix(".exe")
                if n in want:
                    mi = p.info.get("memory_info")
                    found.append({"name": p.info["name"], "pid": p.pid, "memory_mb": round((mi.rss if mi else 0) / 1024**2, 1),
                                  "cpu_percent": cpu_by_pid.get(p.pid, 0.0),
                                  "uptime_min": round((time.time() - (p.info.get("create_time") or time.time())) / 60)})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        found.sort(key=lambda x: x["memory_mb"], reverse=True)
        mine = [w for f in found for w in wins.get(f["pid"], [])]
        hung = [w["title"] for w in mine if w["hung"]]
        return {"count": len(found), "processes": found[:5], "pids": sorted(f["pid"] for f in found),
                "cpu_percent": round(sum(f["cpu_percent"] for f in found), 1),
                "memory_mb": round(sum(f["memory_mb"] for f in found), 1),
                "windows": len(mine), "not_responding": len(hung), "hung_windows": hung[:3]}

    def running_apps(self, include_background: bool = False) -> list[dict]:
        return appfind.running_apps(include_background, sampler=sampler)

    # services
    def svc_lookup(self, name: str) -> dict | None:
        return services.lookup(name)

    def svc_search(self, query: str, limit: int = 8) -> list[dict]:
        return services.search(query, limit)

    def svc_list(self, filt: str, limit: int) -> dict:
        return services.list_services(filt, limit)

    def svc_dependents(self, name: str) -> list[str] | None:
        return services.running_dependents(name)

    def svc_sharing_pid(self, pid: int) -> list[str]:
        if not services.IS_WINDOWS:
            return []
        out = []
        for s in psutil.win_service_iter():
            try:
                if s.pid() == pid:
                    out.append(s.name())
            except Exception:  # noqa: BLE001
                continue
        return out

    def svc_control(self, name: str, action: str) -> dict:
        return services.control(name, action)


LOCAL = LocalHost()


# =============================================================================== remote scripts

_SVC_FN = r"""
function ConvertTo-AgSvc($s) {
  $st = switch ("$($s.State)") { 'Running' {'running'} 'Stopped' {'stopped'} 'Start Pending' {'start_pending'}
        'Stop Pending' {'stop_pending'} 'Paused' {'paused'} default { "$($s.State)".ToLower() } }
  $mode = switch ("$($s.StartMode)") { 'Auto' {'automatic'} 'Manual' {'manual'} 'Disabled' {'disabled'}
          default { "$($s.StartMode)".ToLower() } }
  $procId = $null
  if ($s.ProcessId) { $procId = [int]$s.ProcessId }
  [ordered]@{ name = $s.Name; display_name = $s.DisplayName; status = $st; start_type = $mode; pid = $procId }
}
function Get-AgSvc([string]$n) {
  $q = $n.Replace('\', '\\').Replace("'", "\'")
  Get-CimInstance Win32_Service -Filter "Name='$q'"
}
"""

PS = {
    "hello": r"""
$os = Get-CimInstance Win32_OperatingSystem
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
[ordered]@{
  computer = $env:COMPUTERNAME; os = $os.Caption; version = $os.Version
  ps_version = "$($PSVersionTable.PSVersion)"; user = $id.Name
  is_admin = ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} | ConvertTo-Json -Compress
""",
    "metrics": r"""
$os  = Get-CimInstance Win32_OperatingSystem
$cpu = [double]((Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average)
$total = [double]$os.TotalVisibleMemorySize / 1MB
$free  = [double]$os.FreePhysicalMemory / 1MB
$d = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$($env:SystemDrive)'"
$dt = [double]$d.Size; $df = [double]$d.FreeSpace; $dp = 0
if ($dt -gt 0) { $dp = [math]::Round(($dt - $df) / $dt * 100, 1) }
[ordered]@{
  computer = $env:COMPUTERNAME; os = $os.Caption
  cpu_percent = [math]::Round($cpu, 1)
  memory = [ordered]@{ percent = [math]::Round(($total - $free) / $total * 100, 1); total_gb = [math]::Round($total, 1); used_gb = [math]::Round($total - $free, 1) }
  system_disk = [ordered]@{ mount = "$($env:SystemDrive)\"; percent_used = $dp; free_gb = [math]::Round($df / 1GB, 1) }
  uptime_hours = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 1)
  processes = (Get-Process).Count
} | ConvertTo-Json -Compress
""",
    "snapshot": r"""
$os  = Get-CimInstance Win32_OperatingSystem
$cpu = @(Get-CimInstance Win32_Processor)
$logical  = [int](($cpu | Measure-Object NumberOfLogicalProcessors -Sum).Sum)
$physical = [int](($cpu | Measure-Object NumberOfCores -Sum).Sum)
$load = [math]::Round([double](($cpu | Measure-Object LoadPercentage -Average).Average), 1)
$total = [double]$os.TotalVisibleMemorySize / 1MB
$free  = [double]$os.FreePhysicalMemory / 1MB
$pf = @(Get-CimInstance Win32_PageFileUsage)
$swapTotal = [double](($pf | Measure-Object AllocatedBaseSize -Sum).Sum)
$swapUsed  = [double](($pf | Measure-Object CurrentUsage -Sum).Sum)
$swapPct = 0
if ($swapTotal -gt 0) { $swapPct = [math]::Round($swapUsed / $swapTotal * 100, 1) }
$top = Get-CimInstance Win32_PerfFormattedData_PerfProc_Process |
  Where-Object { $_.Name -ne '_Total' -and $_.Name -ne 'Idle' } |
  Sort-Object PercentProcessorTime -Descending | Select-Object -First 5
[ordered]@{
  host = $env:COMPUTERNAME
  os = "$($os.Caption) ($($os.Version))"
  uptime_hours = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 1)
  cpu = [ordered]@{ percent = $load; logical_cores = $logical; physical_cores = $physical; freq_mhz = $cpu[0].CurrentClockSpeed }
  memory = [ordered]@{ total_gb = [math]::Round($total, 2); used_gb = [math]::Round($total - $free, 2)
                       available_gb = [math]::Round($free, 2); percent = [math]::Round(($total - $free) / $total * 100, 1) }
  swap = [ordered]@{ total_gb = [math]::Round($swapTotal / 1024, 2); percent = $swapPct }
  top_cpu_processes = @($top | ForEach-Object {
    [ordered]@{ name = ($_.Name -replace '#\d+$', ''); pid = [int]$_.IDProcess
                cpu_percent = [math]::Round($_.PercentProcessorTime / [math]::Max($logical, 1), 1) } })
} | ConvertTo-Json -Depth 6 -Compress
""",
    "top_processes": r"""
param([string]$sort_by = 'cpu', [int]$limit = 10)
$cs = Get-CimInstance Win32_ComputerSystem
$logical = [math]::Max([int]$cs.NumberOfLogicalProcessors, 1)
$total = [double]$cs.TotalPhysicalMemory
$key = 'PercentProcessorTime'
if ($sort_by -eq 'memory') { $key = 'WorkingSet' }
$rows = Get-CimInstance Win32_PerfFormattedData_PerfProc_Process |
  Where-Object { $_.Name -ne '_Total' -and $_.Name -ne 'Idle' } |
  Sort-Object $key -Descending | Select-Object -First $limit
[ordered]@{ sorted_by = $sort_by; processes = @($rows | ForEach-Object {
  [ordered]@{ name = ($_.Name -replace '#\d+$', ''); pid = [int]$_.IDProcess
              cpu_percent = [math]::Round($_.PercentProcessorTime / $logical, 1)
              memory_mb = [math]::Round([double]$_.WorkingSet / 1MB, 1)
              memory_percent = [math]::Round([double]$_.WorkingSet / $total * 100, 2) } }) } | ConvertTo-Json -Depth 6 -Compress
""",
    "disk_usage": r"""
$v = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'
[ordered]@{ volumes = @($v | ForEach-Object {
  $t = [double]$_.Size; $f = [double]$_.FreeSpace; $pct = 0
  if ($t -gt 0) { $pct = [math]::Round(($t - $f) / $t * 100, 1) }
  [ordered]@{ mount = "$($_.DeviceID)\"; fstype = $_.FileSystem; total_gb = [math]::Round($t / 1GB, 2)
              used_gb = [math]::Round(($t - $f) / 1GB, 2); free_gb = [math]::Round($f / 1GB, 2); percent_used = $pct } }) } |
  ConvertTo-Json -Depth 6 -Compress
""",
    "network_info": r"""
$ip = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue)
$perf = @(Get-CimInstance Win32_PerfFormattedData_Tcpip_NetworkInterface)
$rx = [double](($perf | Measure-Object BytesReceivedPersec -Sum).Sum)
$tx = [double](($perf | Measure-Object BytesSentPersec -Sum).Sum)
$ifs = @(Get-NetAdapter -ErrorAction SilentlyContinue | ForEach-Object {
  $idx = $_.ifIndex
  [ordered]@{ name = $_.Name; up = ($_.Status -eq 'Up'); speed_mbps = [math]::Round([double]$_.Speed / 1e6)
              ipv4 = @($ip | Where-Object { $_.InterfaceIndex -eq $idx } | ForEach-Object { $_.IPAddress }) } })
[ordered]@{ hostname = $env:COMPUTERNAME
            throughput = [ordered]@{ rx_kbps = [math]::Round($rx * 8 / 1000, 1); tx_kbps = [math]::Round($tx * 8 / 1000, 1) }
            interfaces = $ifs } | ConvertTo-Json -Depth 6 -Compress
""",
    "processes_named": r"""
param([string]$names)
$list = @($names.Split(',') | ForEach-Object { ($_.Trim() -replace '\.exe$', '') } | Where-Object { $_ })
$procs = @(Get-Process -Name $list -ErrorAction SilentlyContinue)
$now = Get-Date
$logical = [math]::Max([int](Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors, 1)
$cpu = @{}
if ($procs.Count) {
  $ids = @($procs | ForEach-Object { $_.Id })
  Get-CimInstance Win32_PerfFormattedData_PerfProc_Process | Where-Object { $ids -contains [int]$_.IDProcess } |
    ForEach-Object { $cpu[[int]$_.IDProcess] = [double]$_.PercentProcessorTime / $logical }
}
$win = @($procs | Where-Object { $_.MainWindowHandle -ne 0 })
$hung = @($win | Where-Object { -not $_.Responding })
$total = 0.0; foreach ($v in $cpu.Values) { $total += $v }
[ordered]@{ count = $procs.Count; pids = @($procs | ForEach-Object { $_.Id } | Sort-Object)
  cpu_percent = [math]::Round($total, 1)
  memory_mb = [math]::Round((($procs | Measure-Object WorkingSet64 -Sum).Sum) / 1MB, 1)
  windows = $win.Count; not_responding = $hung.Count; hung_windows = @($hung | Select-Object -First 3 | ForEach-Object { $_.MainWindowTitle })
  processes = @($procs | Sort-Object WorkingSet64 -Descending | Select-Object -First 5 | ForEach-Object {
  $up = $null
  try { $up = [math]::Round(($now - $_.StartTime).TotalMinutes) } catch { }
  [ordered]@{ name = $_.ProcessName; pid = $_.Id; memory_mb = [math]::Round($_.WorkingSet64 / 1MB, 1)
              cpu_percent = [math]::Round([double]$cpu[$_.Id], 1); uptime_min = $up } }) } |
  ConvertTo-Json -Depth 4 -Compress
""",
    "running_apps": r"""
param([int]$background = 0)
$skip = 'system','registry','idle','smss','csrss','wininit','winlogon','services','lsass','svchost','fontdrvhost','dwm',
        'memory compression','sihost','taskhostw','ctfmon','runtimebroker','conhost','dllhost','wmiprvse','spoolsv',
        'searchindexer','msmpeng','nissrv','audiodg','wudfhost','lsaiso','wsmprovhost'
$ports = @{}
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
  if (-not $ports[[int]$_.OwningProcess]) { $ports[[int]$_.OwningProcess] = @() }
  $ports[[int]$_.OwningProcess] += [int]$_.LocalPort }
$out = @(Get-Process | Where-Object { $skip -notcontains $_.ProcessName.ToLower() -and $_.Id -gt 4 } | Group-Object ProcessName | ForEach-Object {
  $g = $_.Group
  $w = @($g | Where-Object { $_.MainWindowHandle -ne 0 })
  $desc = ($g | Where-Object { $_.Description } | Select-Object -First 1).Description
  $p = @(); foreach ($x in $g) { if ($ports[$x.Id]) { $p += $ports[$x.Id] } }
  [ordered]@{ process = $_.Name; display = $(if ($desc) { $desc } else { $_.Name }); count = $g.Count
              memory_mb = [math]::Round((($g | Measure-Object WorkingSet64 -Sum).Sum) / 1MB, 1); cpu_percent = 0
              has_window = ($w.Count -gt 0); windows = @($w | Select-Object -First 3 | ForEach-Object { $_.MainWindowTitle })
              ports = @($p | Sort-Object -Unique | Select-Object -First 8) } })
$out = @($out | Where-Object { $background -or $_.has_window -or $_.ports.Count } | Sort-Object { -$_.memory_mb })
ConvertTo-Json -InputObject $out -Depth 4 -Compress
""",
    "svc_lookup": "param([string]$name)" + _SVC_FN + r"""
$s = Get-AgSvc $name
$out = $null
if ($s) { $out = ConvertTo-AgSvc $s }
[ordered]@{ service = $out } | ConvertTo-Json -Depth 4 -Compress
""",
    "svc_search": "param([string]$query, [int]$limit = 8)" + _SVC_FN + r"""
$q = $query.ToLower()
$hits = Get-CimInstance Win32_Service |
  Where-Object { $_.Name.ToLower().Contains($q) -or ("$($_.DisplayName)").ToLower().Contains($q) } |
  Select-Object -First $limit
[ordered]@{ services = @($hits | ForEach-Object { ConvertTo-AgSvc $_ }) } | ConvertTo-Json -Depth 4 -Compress
""",
    "svc_list": "param([string]$filter = 'auto_stopped', [int]$limit = 40)" + _SVC_FN + r"""
$all = @(Get-CimInstance Win32_Service | ForEach-Object { ConvertTo-AgSvc $_ })
$keep = @($all | Where-Object {
  $running = $_.status -eq 'running'
  ($filter -eq 'all') -or ($filter -eq 'running' -and $running) -or ($filter -eq 'stopped' -and -not $running) -or
  ($filter -eq 'auto_stopped' -and -not $running -and $_.start_type -eq 'automatic') })
[ordered]@{ filter = $filter; total_services_scanned = $all.Count; matched = [math]::Min($keep.Count, $limit)
            services = @($keep | Select-Object -First $limit) } | ConvertTo-Json -Depth 4 -Compress
""",
    "svc_dependents": r"""
param([string]$name)
$d = @((Get-Service -Name $name -ErrorAction Stop).DependentServices | Where-Object { $_.Status -eq 'Running' } |
  ForEach-Object { $_.Name })
[ordered]@{ dependents = $d } | ConvertTo-Json -Compress
""",
    "svc_sharing_pid": r"""
param([int]$procId)
[ordered]@{ services = @(Get-CimInstance Win32_Service -Filter "ProcessId=$procId" | ForEach-Object { $_.Name }) } |
  ConvertTo-Json -Compress
""",
    # Start / stop / restart with verification done on the remote side (one round trip).
    "svc_control": "param([string]$name, [string]$action)" + _SVC_FN + r"""
function Get-AgState($svc) {
  $svc.Refresh()
  switch ("$($svc.Status)") { 'Running' {'running'} 'Stopped' {'stopped'} 'StartPending' {'start_pending'}
    'StopPending' {'stop_pending'} 'Paused' {'paused'} default { "$($svc.Status)".ToLower() } }
}
$timeout = [TimeSpan]::FromSeconds(25)
try {
  $svc = Get-Service -Name $name -ErrorAction Stop
  $before = Get-AgState $svc
  $want = 'running'
  if ($action -eq 'stop') { $want = 'stopped' }
  if (($action -eq 'start' -and $before -eq 'running') -or ($action -eq 'stop' -and $before -eq 'stopped')) {
    [ordered]@{ service = $svc.Name; display_name = $svc.DisplayName; action = $action; changed = $false
                before = $before; after = $before; verified = $true; note = "already $before; nothing to do" } |
      ConvertTo-Json -Compress
    return
  }
  $note = $null
  if (($action -eq 'stop' -or $action -eq 'restart') -and $before -ne 'stopped') {
    Stop-Service -InputObject $svc -ErrorAction Stop
    try { $svc.WaitForStatus('Stopped', $timeout) } catch { $note = 'service did not stop within 25s' }
  }
  if (-not $note -and ($action -eq 'start' -or $action -eq 'restart')) {
    Start-Service -InputObject $svc -ErrorAction Stop
    try { $svc.WaitForStatus('Running', $timeout) } catch { $note = 'service did not reach running within 25s' }
  }
  $after = Get-AgState $svc
  $w = Get-AgSvc $svc.Name
  $out = [ordered]@{ service = $svc.Name; display_name = $svc.DisplayName; action = $action; changed = $true
                     before = $before; after = $after; verified = ($after -eq $want); pid = $w.ProcessId }
  if ($after -ne $want) { $out['note'] = "expected '$want' but the service is '$after'" }
  if ($note) { $out['note'] = $note }
  $out | ConvertTo-Json -Compress
} catch {
  [ordered]@{ error = $_.Exception.Message } | ConvertTo-Json -Compress
}
""",
}


def _friendly_control_error(msg: str, label: str) -> str:
    low = msg.lower()
    if "cannot open" in low or "access is denied" in low or "access denied" in low:
        return (f"Access denied on {label}: the account Agentica signs in with needs administrator rights there "
                "to control services.")
    if "dependent services" in low:
        return "Other running services depend on this service; stop them first."
    if "disabled" in low:
        return "The service is disabled and cannot be started."
    return msg


# =============================================================================== remote host

class WinRMHost:
    is_local = False

    def __init__(self, machine: dict, password: str) -> None:
        self.machine = machine
        self.label = machine["label"]
        self.address = machine["host"]
        self.os = "windows"
        self.names = {machine["label"].lower(), machine["host"].lower()}
        self._password = password
        self._lock = threading.Lock()
        self._wsman = None
        self._pool = None

    # ---- transport

    def _open(self):
        from pypsrp.powershell import RunspacePool
        from pypsrp.wsman import WSMan
        m = self.machine
        ssl = m["transport"] == "winrm-https"
        self._wsman = WSMan(m["host"], port=m["port"], username=m["username"], password=self._password,
                            ssl=ssl, cert_validation=False, auth="negotiate", encryption="auto",
                            connection_timeout=5, read_timeout=60, operation_timeout=40)
        self._pool = RunspacePool(self._wsman)
        self._pool.open()

    def close(self) -> None:
        try:
            if self._pool is not None:
                self._pool.close()
        except Exception:  # noqa: BLE001
            pass
        self._pool = self._wsman = None

    def _friendly(self, e: Exception) -> str:
        name, text = type(e).__name__, str(e)
        low = text.lower()
        where = f"{self.label} ({self.address}:{self.machine['port']})"
        if name == "AuthenticationError" or "401" in text or "unauthorized" in low or "logon failure" in low:
            return f"Sign-in to {where} failed: check the username and password."
        if "timed out" in low or "timeout" in low:
            return f"{where} did not respond in time. Is it on, and is WinRM enabled (Enable-AgenticaTarget.ps1)?"
        if "connection" in low or "refused" in low or "unreachable" in low or "name or service" in low or "getaddrinfo" in low:
            return f"Cannot connect to {where}. Is it on, and is WinRM enabled (Enable-AgenticaTarget.ps1)?"
        return f"{where}: {name}: {text}"

    def run(self, key: str, **params):
        """Run one of the fixed scripts in PS[key] and return its parsed JSON output."""
        from pypsrp.powershell import PowerShell
        script = PS[key]
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._pool is None:
                        self._open()
                    ps = PowerShell(self._pool)
                    ps.add_script(script)
                    if params:
                        ps.add_parameters(params)
                    out = ps.invoke()
                    text = "".join(str(o) for o in out if o is not None).strip()
                    if not text:
                        errs = "; ".join(str(e) for e in ps.streams.error) or "no output"
                        raise RemoteError(f"{self.label}: {errs}")
                    return json.loads(text)
                except RemoteError:
                    raise
                except Exception as e:  # noqa: BLE001 - transport/auth errors -> reconnect once
                    self.close()
                    msg = self._friendly(e)
                    # a stale session is worth one retry; an unreachable host or bad password is not
                    if attempt == 2 or "Cannot connect" in msg or "did not respond" in msg or "Sign-in" in msg:
                        raise RemoteError(msg) from e

    # ---- operations (same shapes as LocalHost)

    def hello(self) -> dict:
        return self.run("hello")

    def metrics(self) -> dict:
        return self.run("metrics")

    def snapshot(self) -> dict:
        return self.run("snapshot")

    def top_processes(self, sort_by: str, limit: int) -> dict:
        return self.run("top_processes", sort_by=sort_by, limit=limit)

    def disk_usage(self) -> dict:
        return self.run("disk_usage")

    def network_info(self) -> dict:
        return self.run("network_info")

    def processes_named(self, names: list[str]) -> dict:
        return self.run("processes_named", names=",".join(names))

    def running_apps(self, include_background: bool = False) -> list[dict]:
        # Desktop windows of a remote user are not visible over WinRM, so "apps" there = programs
        # with a window in this session OR listening on a port (servers), unless background is asked for.
        res = self.run("running_apps", background=1 if include_background else 0)
        return res if isinstance(res, list) else [res]

    def svc_lookup(self, name: str) -> dict | None:
        return self.run("svc_lookup", name=name).get("service")

    def svc_search(self, query: str, limit: int = 8) -> list[dict]:
        return self.run("svc_search", query=query, limit=limit).get("services", [])

    def svc_list(self, filt: str, limit: int) -> dict:
        res = self.run("svc_list", filter=filt, limit=limit)
        if filt == "auto_stopped":
            res["note"] = ("Automatic services that are stopped are not always faults: delayed-start and "
                           "trigger-start services stop on their own when idle.")
        return res

    def svc_dependents(self, name: str) -> list[str] | None:
        try:
            return self.run("svc_dependents", name=name).get("dependents", [])
        except RemoteError:
            return None

    def svc_sharing_pid(self, pid: int) -> list[str]:
        return self.run("svc_sharing_pid", procId=int(pid)).get("services", [])

    def svc_control(self, name: str, action: str) -> dict:
        t0 = time.perf_counter()
        res = self.run("svc_control", name=name, action=action)
        if "error" in res:
            raise services.ServiceError(_friendly_control_error(res["error"], self.label))
        res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
        return res


class LocalPSHost(WinRMHost):
    """DEV ONLY (AGENTICA_DEV=1): runs the remote scripts on this PC via powershell.exe instead of WinRM."""

    def run(self, key: str, **params):
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as f:
            f.write(PS[key])
            path = f.name
        argv = []
        for k, v in params.items():
            argv += [f"-{k}", str(v)]
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path, *argv],
                               capture_output=True, text=True, timeout=90,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        finally:
            os.unlink(path)
        if not r.stdout.strip():
            raise RemoteError(f"{self.label}: {r.stderr.strip()[:300] or 'no output'}")
        return json.loads(r.stdout)


# =============================================================================== Linux over SSH

LINUX_SCRIPT = (Path(__file__).parent / "linux_remote.py").read_text(encoding="utf-8")
SSH_BOOTSTRAP = ("import sys,json\nd=json.loads(sys.stdin.read())\ng={'__name__':'agentica_remote'}\n"
                 "exec(compile(d['code'],'agentica','exec'),g)\nsys.stdout.write(g['main'](d))")


class SSHHost:
    """A registered Linux machine. Same operations / JSON shapes as LocalHost and WinRMHost."""
    is_local = False

    def __init__(self, machine: dict, password: str) -> None:
        self.machine = machine
        self.label = machine["label"]
        self.address = machine["host"]
        self.os = "linux"
        self.names = {machine["label"].lower(), machine["host"].lower()}
        self._password = password
        self._lock = threading.Lock()
        self._client = None

    def _open(self):
        import paramiko
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())        # trust on first use (no security at this stage)
        c.connect(self.machine["host"], port=self.machine["port"], username=self.machine["username"],
                  password=self._password, timeout=6, banner_timeout=10, auth_timeout=10,
                  look_for_keys=False, allow_agent=False)
        c.get_transport().set_keepalive(30)
        self._client = c

    def close(self) -> None:
        try:
            if self._client is not None:
                self._client.close()
        except Exception:  # noqa: BLE001
            pass
        self._client = None

    def _friendly(self, e: Exception) -> str:
        name, text = type(e).__name__, str(e)
        low = text.lower()
        where = f"{self.label} ({self.address}:{self.machine['port']})"
        if name in ("AuthenticationException", "BadAuthenticationType") or "authentication" in low:
            return f"Sign-in to {where} failed: check the username and password."
        if name in ("timeout", "TimeoutError") or "timed out" in low:
            return f"{where} did not respond in time. Is it on, and is SSH enabled (enable-agentica-target.sh)?"
        if name in ("NoValidConnectionsError", "ConnectionRefusedError", "gaierror") or "unable to connect" in low \
                or "refused" in low or "getaddrinfo" in low:
            return f"Cannot connect to {where}. Is it on, and is SSH enabled (enable-agentica-target.sh)?"
        return f"{where}: {name}: {text}"

    def run(self, op: str, **args):
        payload = json.dumps({"code": LINUX_SCRIPT, "op": op, "args": args, "pw": self._password})
        cmd = "python3 -c " + shlex.quote(SSH_BOOTSTRAP)
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._client is None:
                        self._open()
                    stdin, stdout, stderr = self._client.exec_command(cmd, timeout=90)
                    stdin.write(payload)
                    stdin.channel.shutdown_write()
                    out = stdout.read().decode("utf-8", "replace")
                    err = stderr.read().decode("utf-8", "replace")
                    rc = stdout.channel.recv_exit_status()
                    break
                except Exception as e:  # noqa: BLE001 - stale session -> one reconnect; bad login / down -> fail now
                    self.close()
                    msg = self._friendly(e)
                    if attempt == 2 or "Sign-in" in msg or "Cannot connect" in msg or "did not respond" in msg:
                        raise RemoteError(msg) from e
        if rc == 127 or "python3: command not found" in err or "python3: not found" in err:
            raise RemoteError(f"python3 is not installed on {self.label}. Install it (e.g. sudo apt install python3) "
                              "or run enable-agentica-target.sh.")
        try:
            res = json.loads(out)
        except ValueError:
            raise RemoteError(f"{self.label}: unexpected output ({(err or out).strip()[:200] or 'empty'})") from None
        if "error" in res:
            raise RemoteError(f"{self.label}: {res['error']}")
        return res["result"]

    # same operations as LocalHost / WinRMHost
    def hello(self) -> dict:
        return self.run("hello")

    def metrics(self) -> dict:
        return self.run("metrics")

    def snapshot(self) -> dict:
        return self.run("snapshot")

    def top_processes(self, sort_by: str, limit: int) -> dict:
        return self.run("top_processes", sort_by=sort_by, limit=limit)

    def disk_usage(self) -> dict:
        return self.run("disk_usage")

    def network_info(self) -> dict:
        return self.run("network_info")

    def processes_named(self, names: list[str]) -> dict:
        return self.run("processes_named", names=",".join(names))

    def running_apps(self, include_background: bool = False) -> list[dict]:
        return self.run("running_apps", background=1 if include_background else 0)

    def svc_lookup(self, name: str) -> dict | None:
        return self.run("svc_lookup", name=name).get("service")

    def svc_search(self, query: str, limit: int = 8) -> list[dict]:
        return self.run("svc_search", query=query, limit=limit).get("services", [])

    def svc_list(self, filt: str, limit: int) -> dict:
        res = self.run("svc_list", filter=filt, limit=limit)
        if filt == "auto_stopped":
            res["note"] = "On Linux this lists failed units (systemctl --state=failed)."
        return res

    def svc_dependents(self, name: str) -> list[str] | None:
        try:
            return self.run("svc_dependents", name=name).get("dependents", [])
        except RemoteError:
            return None

    def svc_sharing_pid(self, pid: int) -> list[str]:
        return []

    def svc_control(self, name: str, action: str) -> dict:
        t0 = time.perf_counter()
        res = self.run("svc_control", name=name, action=action)
        if "error" in res:
            raise services.ServiceError(res["error"])
        res["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
        return res


# =============================================================================== registry

def password_key(mid: str) -> str:
    return f"machine:{mid}"


def get_password(mid: str) -> str | None:
    try:
        return keyring.get_password(KEYRING_SERVICE, password_key(mid))
    except Exception:  # noqa: BLE001
        return None


def set_password(mid: str, password: str) -> None:
    keyring.set_password(KEYRING_SERVICE, password_key(mid), password)


def delete_password(mid: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, password_key(mid))
    except Exception:  # noqa: BLE001
        pass


class HostRegistry:
    def __init__(self, store, port_state=None) -> None:
        self.store = store
        self.port_state = port_state or (lambda mid: None)   # last reachability probe for a machine
        self._cache: dict[str, tuple[tuple, WinRMHost]] = {}
        self._lock = threading.Lock()

    def names(self) -> list[str]:
        return ["local"] + [m["label"] for m in self.store.machines()]

    def for_machine(self, m: dict, use_probe: bool = True) -> tuple[WinRMHost | None, str | None]:
        if m["transport"] == "local-ps":
            if not DEV:
                return None, TargetError(f"'{m['label']}' uses the dev-only loopback transport; start with AGENTICA_DEV=1.")
            with self._lock:
                hit = self._cache.get(m["id"])
                if not hit:
                    hit = (("local-ps",), LocalPSHost({**m, "username": "loopback"}, ""))
                    self._cache[m["id"]] = hit
            return hit[1], None
        pw = get_password(m["id"])
        if not m.get("username") or pw is None:
            return None, TargetError(f"No credentials set for '{m['label']}'. Open it under Machines and enter the "
                                     "username and password Agentica should sign in with.")
        probe = (self.port_state(m["id"]) or {}) if use_probe else {}
        if probe.get("state") == "unreachable" and time.time() - probe.get("checked", 0) < 30:
            return None, TargetError.state(f"'{m['label']}' ({m['host']}) is unreachable: port {m['port']} did not "
                                           f"answer the last check ({probe.get('error') or 'no response'}).")
        key = (m["host"], m["port"], m["transport"], m["username"], hash(pw))
        with self._lock:
            hit = self._cache.get(m["id"])
            if hit and hit[0] == key:
                return hit[1], None
            if hit:
                hit[1].close()
            host = SSHHost(m, pw) if m["transport"] == "ssh" else WinRMHost(m, pw)
            self._cache[m["id"]] = (key, host)
            return host, None

    def resolve(self, target: str | None):
        """-> (host, error). `target` may be 'local', a label, a hostname or an IP."""
        t = (target or "local").strip()
        if t.lower() in LOCAL_NAMES:
            return LOCAL, None
        m = self.store.machine_by_name(t)
        if not m:
            known = ", ".join(self.names())
            return None, TargetError(f"Unknown machine '{t}'. Registered machines: {known}.")
        return self.for_machine(m)

    def forget(self, mid: str) -> None:
        with self._lock:
            hit = self._cache.pop(mid, None)
        if hit:
            hit[1].close()
