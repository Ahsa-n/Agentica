"""
Agentica's Linux-side script. It is SENT over SSH and run with `python3` on the target for every
operation (nothing is installed there). Standard library only; Python 3.6+.

    bootstrap (hosts.SSH_BOOTSTRAP) reads {"code", "op", "args", "pw"} as JSON from stdin,
    executes this file and prints main(payload) -> '{"result": ...}' or '{"error": "..."}'.

Every operation returns JSON in the same shape as the local (psutil) and Windows (WinRM)
implementations, so tools, policy and UI never care which OS answered.

Test hook: if AGENTICA_TEST_ROOT is set, /proc, /sys and /etc are read below that folder; command
outputs (systemctl / ss / ip / sudo) come from <root>/commands.json and the second samples that would
need waiting (cpu, network, clock) from <root>/meta.json. Used by the tests on Windows only.
"""
import json
import os
import re
import socket
import subprocess
import sys
import time

ROOT = os.environ.get("AGENTICA_TEST_ROOT", "")
PROC, SYS, ETC = ROOT + "/proc", ROOT + "/sys", ROOT + "/etc"
D = {}                       # the payload (op, args, sudo password)
_FIX = {}


def _fixture(name):
    if name not in _FIX:
        with open(os.path.join(ROOT, name)) as f:
            _FIX[name] = json.load(f)
    return _FIX[name]


def _fake():
    return _fixture("commands.json")


def _meta():
    return _fixture("meta.json")


def run(cmd, inp=None, timeout=60):
    """Run a command (argv list, never a shell). -> (returncode, stdout, stderr)"""
    if ROOT:
        key = " ".join(cmd)
        for pattern, res in _fake().items():
            if re.fullmatch(pattern, key):
                return res[0], res[1], res[2]
        return 1, "", "test fixture has no output for: " + key
    try:
        r = subprocess.run(cmd, input=inp, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, "", cmd[0] + ": command not found"


def read(path):
    with open(path) as f:
        return f.read()


def sysconf(name, default):
    try:
        return os.sysconf(name)
    except (AttributeError, ValueError, OSError):
        return default


CLK_TCK = sysconf("SC_CLK_TCK", 100)
PAGE = sysconf("SC_PAGE_SIZE", 4096)


def gb(n):
    return round(n / 1024.0 ** 3, 2)


def statvfs(path):
    if ROOT:
        f = _meta()["statvfs"][path]
        return f["total"], f["free"]
    st = os.statvfs(path)
    return st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize


# ----------------------------------------------------------------------------- cpu / memory / processes

def cpu_times():
    out = {}
    for line in read(PROC + "/stat").splitlines():
        if line.startswith("cpu"):
            p = line.split()
            v = [int(x) for x in p[1:]]
            idle = v[3] + (v[4] if len(v) > 4 else 0)
            out[p[0]] = (idle, sum(v[:8]))
    return out


def cpu_percent(interval=0.5):
    a = cpu_times()
    if ROOT:
        b = {k: tuple(v) for k, v in _meta()["stat2"].items()}
    else:
        time.sleep(interval)
        b = cpu_times()
    pct = {}
    for k in b:
        di, dt = b[k][0] - a.get(k, (0, 0))[0], b[k][1] - a.get(k, (0, 0))[1]
        pct[k] = round(100.0 * (1 - di / dt), 1) if dt > 0 else 0.0
    cores = [pct[k] for k in sorted((k for k in pct if k != "cpu"), key=lambda x: int(x[3:]))]
    return pct.get("cpu", 0.0), cores


def meminfo():
    m = {}
    for line in read(PROC + "/meminfo").splitlines():
        k, _, rest = line.partition(":")
        m[k] = int(rest.split()[0]) * 1024 if rest.split() else 0
    return m


def boot_time():
    for line in read(PROC + "/stat").splitlines():
        if line.startswith("btime"):
            return int(line.split()[1])
    return int(time.time() - float(read(PROC + "/uptime").split()[0]))


def pids():
    return sorted(int(p) for p in os.listdir(PROC) if p.isdigit())


def proc_info(pid):
    """comm, utime+stime ticks, rss bytes, start time (epoch) — None if the process vanished."""
    try:
        raw = read("%s/%d/stat" % (PROC, pid))
        comm = raw[raw.index("(") + 1: raw.rindex(")")]
        rest = raw[raw.rindex(")") + 2:].split()
        ticks = int(rest[11]) + int(rest[12])
        start = boot_time() + int(rest[19]) / float(CLK_TCK)
        rss = int(read("%s/%d/statm" % (PROC, pid)).split()[1]) * PAGE
        return {"pid": pid, "name": comm, "ticks": ticks, "rss": rss, "start": start}
    except (OSError, ValueError, IndexError):
        return None


def processes(sample=0.5):
    """All processes with cpu % over `sample` seconds (normalised by core count, like Task Manager)."""
    first = {p: proc_info(p) for p in pids()}
    if ROOT:
        cpu = _meta().get("cpu", {})
        out = []
        for pid, info in first.items():
            if info:
                info["cpu"] = float(cpu.get(str(pid), 0.0))
                out.append(info)
        return out
    time.sleep(sample)
    out = []
    for p in pids():
        a, b = first.get(p), proc_info(p)
        if not (a and b):
            continue
        b["cpu"] = round(100.0 * (b["ticks"] - a["ticks"]) / CLK_TCK / sample / max(ncpu(), 1), 1)
        out.append(b)
    return out


def os_name():
    try:
        for line in read(ETC + "/os-release").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "Linux"


def uptime_s():
    return float(read(PROC + "/uptime").split()[0])


def ncpu():
    return int(_meta()["ncpu"]) if ROOT else (os.cpu_count() or 1)


def physical_cores():
    try:
        ids = set()
        phys = core = None
        for line in read(PROC + "/cpuinfo").splitlines():
            if line.startswith("physical id"):
                phys = line.split(":")[1].strip()
            elif line.startswith("core id"):
                core = line.split(":")[1].strip()
                ids.add((phys, core))
        return len(ids) or None
    except OSError:
        return None


def freq_mhz():
    try:
        for line in read(PROC + "/cpuinfo").splitlines():
            if line.lower().startswith("cpu mhz"):
                return round(float(line.split(":")[1]))
    except (OSError, ValueError):
        pass
    return None


def hostname():
    if ROOT:
        return read(ETC + "/hostname").strip()
    return socket.gethostname()


# ----------------------------------------------------------------------------- sudo + systemd

def is_root():
    return (not ROOT) and hasattr(os, "geteuid") and os.geteuid() == 0


def sudo(cmd):
    """Run with root rights: directly as root, `sudo -n` (NOPASSWD rule), else `sudo -S` with the saved password."""
    if is_root():
        return run(cmd)
    rc, out, err = run(["sudo", "-n"] + cmd)
    if rc != 0 and re.search(r"password is required|a terminal is required", err) and D.get("pw"):
        rc, out, err = run(["sudo", "-S", "-p", ""] + cmd, inp=D["pw"] + "\n")
    return rc, out, err


_STATE = {"active": "running", "inactive": "stopped", "failed": "failed", "activating": "start_pending",
          "deactivating": "stop_pending", "reloading": "running"}
_START = {"enabled": "automatic", "enabled-runtime": "automatic", "disabled": "disabled", "masked": "disabled",
          "static": "manual", "indirect": "manual", "generated": "automatic"}


def svc_lookup(name):
    rc, out, _ = run(["systemctl", "show", name, "--no-pager",
                      "--property=Id,Description,LoadState,ActiveState,SubState,UnitFileState,MainPID"])
    props = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
    if not props or props.get("LoadState") in ("not-found", None, ""):
        return None
    pid = int(props.get("MainPID") or 0)
    return {"name": props.get("Id", name), "display_name": props.get("Description", ""),
            "status": _STATE.get(props.get("ActiveState", ""), props.get("ActiveState")),
            "start_type": _START.get(props.get("UnitFileState", ""), props.get("UnitFileState")),
            "pid": pid or None, "sub_state": props.get("SubState")}


def _units(state=None):
    cmd = ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain", "--no-pager"]
    if state:
        cmd.append("--state=" + state)
    rc, out, _ = run(cmd)
    rows = []
    for line in out.splitlines():
        p = line.split(None, 4)
        if len(p) >= 4:
            rows.append({"name": p[0], "status": _STATE.get(p[2], p[2]), "sub_state": p[3],
                         "display_name": p[4] if len(p) > 4 else ""})
    return rows


def svc_search(query, limit=8):
    q = query.lower()
    return [u for u in _units() if q in u["name"].lower() or q in u["display_name"].lower()][:limit]


def svc_list(filter="auto_stopped", limit=40):
    state = {"auto_stopped": "failed", "running": "running", "stopped": "inactive", "all": None}[filter]
    rows = _units(state)
    return {"filter": filter, "total_services_scanned": len(_units()) if state else len(rows),
            "matched": min(len(rows), limit), "services": rows[:limit]}


def svc_dependents(name):
    rc, out, _ = run(["systemctl", "list-dependencies", "--reverse", "--plain", "--no-pager", name])
    deps = [l.strip() for l in out.splitlines()[1:] if l.strip().endswith(".service")]
    if not deps:
        return {"dependents": []}
    rc, out, _ = run(["systemctl", "is-active"] + deps)
    states = out.split()
    return {"dependents": [d for d, s in zip(deps, states) if s == "active"]}


def _perm_error(err):
    low = err.lower()
    return any(s in low for s in ("authentication", "incorrect password", "not in the sudoers", "may not run sudo",
                                  "access denied", "permission denied", "sudo: a password is required",
                                  "is not allowed to execute", "sorry, user", "sudo: no tty present"))


def svc_control(name, action):
    info = svc_lookup(name)
    if info is None:
        return {"error": "No service named '%s'." % name}
    before = info["status"]
    want = "stopped" if action == "stop" else "running"
    if (action == "start" and before == "running") or (action == "stop" and before == "stopped"):
        return {"service": info["name"], "display_name": info["display_name"], "action": action, "changed": False,
                "before": before, "after": before, "verified": True, "note": "already %s; nothing to do" % before}
    rc, out, err = sudo(["systemctl", action, name])
    if rc != 0:
        if _perm_error(err):
            return {"error": "Permission denied: the account Agentica signs in with needs sudo rights for systemctl "
                             "on this machine (run enable-agentica-target.sh)."}
        return {"error": (err or out).strip() or "systemctl %s failed" % action}
    deadline = time.time() + (0 if ROOT else 25)
    after = svc_lookup(name) or {}
    while after.get("status") != want and time.time() < deadline:
        time.sleep(0.25)
        after = svc_lookup(name) or {}
    res = {"service": info["name"], "display_name": info["display_name"], "action": action, "changed": True,
           "before": before, "after": after.get("status"), "verified": after.get("status") == want,
           "pid": after.get("pid")}
    if not res["verified"]:
        res["note"] = "expected '%s' but the service is '%s'" % (want, after.get("status"))
    return res


# ----------------------------------------------------------------------------- disks / network

REAL_FS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "vfat", "exfat", "ntfs", "ntfs3", "fuseblk", "f2fs",
           "jfs", "reiserfs", "hfsplus"}


def disk_usage():
    seen, vols = set(), []
    for line in read(PROC + "/mounts").splitlines():
        p = line.split()
        if len(p) < 3 or p[2] not in REAL_FS or p[0] in seen:
            continue
        seen.add(p[0])
        mount = p[1].replace("\\040", " ")
        try:
            total, free = statvfs(mount)
        except (OSError, KeyError):
            continue
        if not total:
            continue
        vols.append({"mount": mount, "fstype": p[2], "total_gb": gb(total), "used_gb": gb(total - free),
                     "free_gb": gb(free), "percent_used": round(100.0 * (total - free) / total, 1)})
    return {"volumes": vols}


def net_bytes():
    rx = tx = 0
    for line in read(PROC + "/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        if name.strip() == "lo":
            continue
        v = rest.split()
        rx += int(v[0])
        tx += int(v[8])
    return rx, tx


def network_info():
    a = net_bytes()
    if ROOT:
        b = tuple(_meta()["netdev2"])
    else:
        time.sleep(0.5)
        b = net_bytes()
    rx, tx = (b[0] - a[0]) / 0.5, (b[1] - a[1]) / 0.5
    v4 = {}
    rc, out, _ = run(["ip", "-4", "-o", "addr", "show"])
    for line in out.splitlines():
        m = re.match(r"\d+:\s+(\S+)\s+inet\s+([\d.]+)/", line)
        if m:
            v4.setdefault(m.group(1), []).append(m.group(2))
    ifaces = []
    for name in sorted(os.listdir(SYS + "/class/net")):
        if name == "lo":
            continue
        base = "%s/class/net/%s/" % (SYS, name)
        try:
            up = read(base + "operstate").strip() == "up"
        except OSError:
            up = False
        try:
            speed = int(read(base + "speed").strip())
        except (OSError, ValueError):
            speed = 0
        if up or v4.get(name):
            ifaces.append({"name": name, "up": up, "speed_mbps": max(speed, 0), "ipv4": v4.get(name, [])})
    return {"hostname": hostname(), "throughput": {"rx_kbps": round(rx * 8 / 1000, 1), "tx_kbps": round(tx * 8 / 1000, 1)},
            "interfaces": ifaces}


def listening_ports():
    """{pid: [ports]} from `ss -ltnpH` (pids of other users' sockets need root; those are simply missing)."""
    rc, out, _ = run(["ss", "-ltnpH"])
    by = {}
    for line in out.splitlines():
        p = line.split()
        if len(p) < 4:
            continue
        try:
            port = int(p[3].rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        for pid in re.findall(r"pid=(\d+)", line):
            by.setdefault(int(pid), set()).add(port)
    return {k: sorted(v) for k, v in by.items()}


# ----------------------------------------------------------------------------- operations

def op_hello():
    rc, _, _ = (0, "", "") if is_root() else run(["sudo", "-n", "true"])
    admin = is_root() or rc == 0
    if not admin and D.get("pw"):
        rc, _, _ = run(["sudo", "-S", "-p", "", "-v"], inp=D["pw"] + "\n")
        admin = rc == 0
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "?"
    return {"computer": hostname(), "os": os_name(), "version": read(PROC + "/sys/kernel/osrelease").strip(),
            "ps_version": "python " + sys.version.split()[0], "user": user, "is_admin": bool(admin)}


def op_metrics():
    total, _ = cpu_percent(0.4)
    m = meminfo()
    t, a = m.get("MemTotal", 0), m.get("MemAvailable", m.get("MemFree", 0))
    dt, df = statvfs("/")
    return {"computer": hostname(), "os": os_name(), "cpu_percent": total,
            "memory": {"percent": round(100.0 * (t - a) / t, 1) if t else 0, "total_gb": round(t / 1024.0 ** 3, 1),
                       "used_gb": round((t - a) / 1024.0 ** 3, 1)},
            "system_disk": {"mount": "/", "percent_used": round(100.0 * (dt - df) / dt, 1) if dt else 0,
                            "free_gb": round(df / 1024.0 ** 3, 1)},
            "uptime_hours": round(uptime_s() / 3600, 1), "processes": len(pids())}


def op_snapshot():
    total, cores = cpu_percent(0.5)
    m = meminfo()
    t, a = m.get("MemTotal", 0), m.get("MemAvailable", m.get("MemFree", 0))
    st, sf = m.get("SwapTotal", 0), m.get("SwapFree", 0)
    procs = sorted(processes(0.5), key=lambda p: p["cpu"], reverse=True)[:5]
    return {"host": hostname(), "os": os_name(), "uptime_hours": round(uptime_s() / 3600, 1),
            "cpu": {"percent": total, "logical_cores": ncpu(), "physical_cores": physical_cores(),
                    "busiest_core_percent": max(cores) if cores else None, "freq_mhz": freq_mhz()},
            "memory": {"total_gb": gb(t), "used_gb": gb(t - a), "available_gb": gb(a),
                       "percent": round(100.0 * (t - a) / t, 1) if t else 0},
            "swap": {"total_gb": gb(st), "percent": round(100.0 * (st - sf) / st, 1) if st else 0},
            "top_cpu_processes": [{"name": p["name"], "pid": p["pid"], "cpu_percent": p["cpu"]} for p in procs]}


def op_top_processes(sort_by="cpu", limit=10):
    procs = processes(0.5)
    procs.sort(key=(lambda p: p["cpu"]) if sort_by == "cpu" else (lambda p: p["rss"]), reverse=True)
    t = meminfo().get("MemTotal", 1)
    return {"sorted_by": sort_by, "processes": [
        {"name": p["name"], "pid": p["pid"], "cpu_percent": p["cpu"], "memory_mb": round(p["rss"] / 1024.0 ** 2, 1),
         "memory_percent": round(100.0 * p["rss"] / t, 2)} for p in procs[:int(limit)]]}


def _norm(n):
    return re.sub(r"\.exe$", "", n.strip().lower())[:15]          # /proc comm is truncated to 15 chars


def op_processes_named(names):
    want = {_norm(n) for n in names.split(",") if n.strip()}
    found = [p for p in processes(0.5) if p["name"].lower()[:15] in want]
    found.sort(key=lambda p: p["rss"], reverse=True)
    now = float(_meta()["now"]) if ROOT else time.time()
    return {"count": len(found), "pids": sorted(p["pid"] for p in found),
            "cpu_percent": round(sum(p["cpu"] for p in found), 1),
            "memory_mb": round(sum(p["rss"] for p in found) / 1024.0 ** 2, 1),
            "windows": 0, "not_responding": 0, "hung_windows": [],
            "processes": [{"name": p["name"], "pid": p["pid"], "memory_mb": round(p["rss"] / 1024.0 ** 2, 1),
                           "cpu_percent": p["cpu"], "uptime_min": round((now - p["start"]) / 60)} for p in found[:5]]}


SKIP = {"systemd", "kthreadd", "rcu_sched", "rcu_preempt", "ksoftirqd", "kworker", "migration", "watchdog", "cpuhp",
        "idle_inject", "kauditd", "khungtaskd", "oom_reaper", "kcompactd0", "khugepaged", "kswapd0", "sshd", "sd-pam",
        "(sd-pam)", "bash", "sh", "python3", "sudo", "agetty", "dbus-daemon", "systemd-journal", "systemd-udevd",
        "systemd-logind", "systemd-resolve", "systemd-network", "systemd-timesyn", "polkitd", "cron", "rsyslogd"}


def op_running_apps(background=0):
    ports = listening_ports()
    groups = {}
    for p in processes(0.5):
        n = p["name"]
        base = re.split(r"[/:]", n)[0]
        if base in SKIP or base.startswith("kworker") or base.startswith("ksoftirqd"):
            continue
        g = groups.setdefault(n, {"process": n, "display": n, "count": 0, "memory_mb": 0.0, "cpu_percent": 0.0,
                                  "has_window": False, "windows": [], "ports": set()})
        g["count"] += 1
        g["memory_mb"] += p["rss"] / 1024.0 ** 2
        g["cpu_percent"] += p["cpu"]
        g["ports"].update(ports.get(p["pid"], []))
    out = []
    for g in groups.values():
        if not int(background) and not g["ports"]:
            continue
        g["ports"] = sorted(g["ports"])[:8]
        g["memory_mb"] = round(g["memory_mb"], 1)
        g["cpu_percent"] = round(g["cpu_percent"], 1)
        out.append(g)
    out.sort(key=lambda a: -a["memory_mb"])
    return out


OPS = {
    "hello": op_hello, "metrics": op_metrics, "snapshot": op_snapshot, "top_processes": op_top_processes,
    "disk_usage": lambda: disk_usage(), "network_info": lambda: network_info(),
    "svc_lookup": lambda name: {"service": svc_lookup(name)},
    "svc_search": lambda query, limit=8: {"services": svc_search(query, int(limit))},
    "svc_list": lambda filter="auto_stopped", limit=40: svc_list(filter, int(limit)),
    "svc_dependents": svc_dependents, "svc_sharing_pid": lambda procId=0: {"services": []},
    "svc_control": svc_control, "processes_named": op_processes_named, "running_apps": op_running_apps,
}


def main(payload):
    global D
    D = payload
    op = payload.get("op")
    if op not in OPS:
        return json.dumps({"error": "unknown operation " + str(op)})
    args = payload.get("args") or {}
    try:
        return json.dumps({"result": OPS[op](**args)})
    except Exception as e:  # noqa: BLE001 - report, never hang the SSH call
        return json.dumps({"error": "%s: %s" % (type(e).__name__, e)})
