"""
Linux over SSH, without a Linux machine: a real SSH server (tests/fake_ssh_server.py, paramiko) runs
the exact script Agentica sends, against recorded Linux data (tests/fixtures/linux).

    python tests/linux_ssh.py

Checks every operation's result and that its JSON shape matches the local tools, sudo / permission
handling, sign-in and connection errors, reconnecting, and the .service-suffix hardline match.
"""
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fake_ssh_server                                   # noqa: E402
from hosts import LOCAL, RemoteError, SSHHost            # noqa: E402
import services                                          # noqa: E402

HOST, PORT = "127.0.0.2", 2223
threading.Thread(target=fake_ssh_server.serve, args=(HOST, PORT, "agentica", "secret"), daemon=True).start()
time.sleep(2)

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def keys(d):
    return sorted(d) if isinstance(d, dict) else type(d).__name__


m = {"label": "web-01", "host": HOST, "port": PORT, "transport": "ssh", "username": "agentica"}
h = SSHHost(m, "secret")

hello = h.hello()
check("sign in + hello", hello["computer"] == "web-01" and hello["os"] == "Ubuntu 22.04.4 LTS", hello["os"])
s = h.snapshot()
check("snapshot: same shape as local", keys(s) == keys(LOCAL.snapshot()) and keys(s["cpu"]) == keys(LOCAL.snapshot()["cpu"]))
check("cpu 25 %, busiest core 40 %, 2 physical cores",
      s["cpu"]["percent"] == 25.0 and s["cpu"]["busiest_core_percent"] == 40.0 and s["cpu"]["physical_cores"] == 2)
check("memory 62.3 %, swap 12.5 %", s["memory"]["percent"] == 62.3 and s["swap"]["percent"] == 12.5)
d = h.disk_usage()
check("disks: real filesystems only, duplicates skipped",
      [v["mount"] for v in d["volumes"]] == ["/", "/boot/efi", "/srv/data"], [v["mount"] for v in d["volumes"]])
n = h.network_info()
check("network: eth0 up 1000 Mb/s, 10 Mb/s in", n["interfaces"][0]["ipv4"] == ["10.0.0.21"] and n["throughput"]["rx_kbps"] == 10000.0)
t = h.top_processes("memory", 2)
check("top processes by memory", [p["name"] for p in t["processes"]] == ["postgres", "postgres"])
svc = h.svc_lookup("nginx")
check("service lookup: same keys as local", set(keys(LOCAL.svc_lookup("wcncsvc") or {})) <= set(keys(svc)) and svc["status"] == "running")
check("missing service -> None", h.svc_lookup("does-not-exist") is None)
check("failed units", [x["name"] for x in h.svc_list("auto_stopped", 10)["services"]] == ["redis-server.service"])
check("running dependents", h.svc_dependents("postgresql") == ["app-backend.service"])
p = h.processes_named(["nginx", "postgres"])
check("processes_named: same shape as local", keys(p) == keys(LOCAL.processes_named(["python"])) and p["count"] == 4)
apps = h.running_apps(False)
check("running apps with listening ports", {a["process"]: a["ports"] for a in apps} == {"postgres": [5432], "nginx": [80, 443]})
noop = h.svc_control("nginx", "start")
check("control: no-op start detected", noop["changed"] is False and noop["verified"] is True)
try:
    h.svc_control("redis-server", "start")
    check("control: sudo refusal reported", False)
except services.ServiceError as e:
    check("control: sudo refusal -> clear permission message", "needs sudo rights" in str(e))
h._client.close()
check("reconnects after a dropped connection", h.disk_usage()["volumes"][0]["mount"] == "/")
try:
    SSHHost(m, "wrong").hello()
    check("wrong password refused", False)
except RemoteError as e:
    check("wrong password -> clear message", "check the username and password" in str(e))
try:
    SSHHost({**m, "port": 2299}, "secret").hello()
    check("closed port refused", False)
except RemoteError as e:
    check("nothing listening -> clear message", "Cannot connect" in str(e))

from policy import HARDLINE_LINUX, PolicyEngine                       # noqa: E402
pe = PolicyEngine.__new__(PolicyEngine)
pe.cfg = {"protected_services": []}
check("hardline matches 'ssh.service' (suffix ignored)", PolicyEngine._protected(pe, "ssh.service") and "ssh" in HARDLINE_LINUX)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
