"""Host telemetry: one background thread samples psutil once per second."""
from __future__ import annotations

import platform
import socket
import threading
import time
from collections import deque

import psutil

HISTORY = 90  # samples kept (1 per second)


class Sampler:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.cpu = 0.0
        self.per_core: list[float] = []
        self.cpu_hist: deque[float] = deque(maxlen=HISTORY)
        self.mem_hist: deque[float] = deque(maxlen=HISTORY)
        self.rx_rate = 0.0
        self.tx_rate = 0.0
        self.rx_hist: deque[float] = deque(maxlen=HISTORY)
        self.tx_hist: deque[float] = deque(maxlen=HISTORY)
        self.procs: list[dict] = []
        self.ncpu = psutil.cpu_count(logical=True) or 1
        self.seq = 0
        self._stop = threading.Event()

    def start(self) -> None:
        psutil.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)
        threading.Thread(target=self._run, name="telemetry", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        last_net = psutil.net_io_counters()
        last_t = time.monotonic()
        tick = 0
        while not self._stop.wait(1.0):
            now = time.monotonic()
            dt = max(now - last_t, 1e-3)
            cpu = psutil.cpu_percent(None)
            cores = psutil.cpu_percent(None, percpu=True)
            mem = psutil.virtual_memory().percent
            net = psutil.net_io_counters()
            rx = max(net.bytes_recv - last_net.bytes_recv, 0) / dt
            tx = max(net.bytes_sent - last_net.bytes_sent, 0) / dt
            last_net, last_t = net, now
            procs = self._sample_procs() if tick % 2 == 0 else None
            with self.lock:
                self.cpu, self.per_core = cpu, cores
                self.cpu_hist.append(cpu)
                self.mem_hist.append(mem)
                self.rx_rate, self.tx_rate = rx, tx
                self.rx_hist.append(rx)
                self.tx_hist.append(tx)
                if procs is not None:
                    self.procs = procs
                self.seq += 1
            tick += 1

    def _sample_procs(self) -> list[dict]:
        out = []
        for p in psutil.process_iter(["pid", "name", "memory_info", "status"]):
            try:
                if p.pid == 0:
                    continue
                cpu = p.cpu_percent(None) / self.ncpu
                mi = p.info.get("memory_info")
                out.append({
                    "pid": p.pid,
                    "name": p.info.get("name") or f"pid {p.pid}",
                    "cpu": round(cpu, 1),
                    "rss": mi.rss if mi else 0,
                    "status": p.info.get("status"),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return out


sampler = Sampler()
HOSTNAME = socket.gethostname()


def uptime() -> int:
    return int(time.time() - psutil.boot_time())


def os_label() -> str:
    if platform.system() == "Windows":
        ver = platform.version()
        try:
            build = int(ver.split(".")[-1])
        except ValueError:
            build = 0
        name = "Windows 11" if build >= 22000 else f"Windows {platform.release()}"
        return f"{name} ({ver})"
    return f"{platform.system()} {platform.release()}"


def disks() -> list[dict]:
    out = []
    for part in psutil.disk_partitions(all=False):
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            u = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        out.append({"mount": part.mountpoint, "fstype": part.fstype, "total": u.total,
                    "used": u.used, "free": u.free, "percent": u.percent})
    return out


def telemetry_payload() -> dict:
    vm = psutil.virtual_memory()
    with sampler.lock:
        data = {
            "cpu": {
                "percent": sampler.cpu,
                "per_core": list(sampler.per_core),
                "history": list(sampler.cpu_hist),
                "logical": psutil.cpu_count(logical=True),
                "physical": psutil.cpu_count(logical=False),
            },
            "net": {
                "rx": sampler.rx_rate, "tx": sampler.tx_rate,
                "rx_hist": list(sampler.rx_hist), "tx_hist": list(sampler.tx_hist),
            },
            "mem_hist": list(sampler.mem_hist),
            "procs": sorted(sampler.procs, key=lambda p: p["cpu"], reverse=True)[:6],
        }
    data["memory"] = {"total": vm.total, "used": vm.total - vm.available, "percent": vm.percent}
    data["disks"] = disks()
    data["host"] = {"hostname": HOSTNAME, "os": os_label(), "uptime": uptime()}
    data["ts"] = time.time()
    return data
