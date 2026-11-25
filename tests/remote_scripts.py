"""Runs every remote (WinRM) PowerShell script on this PC via powershell.exe and compares its JSON with the local tools.

    python tests/remote_scripts.py
"""
import json, os, subprocess, sys, tempfile, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import hosts
from hosts import PS, WinRMHost, LOCAL

class PSLocalRunner(WinRMHost):
    """Same scripts as the WinRM host, executed locally through powershell.exe."""
    def run(self, key, **params):
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as f:
            f.write(PS[key]); path = f.name
        args = []
        for k, v in params.items(): args += [f"-{k}", str(v)]
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path, *args],
                               capture_output=True, text=True, timeout=90)
        finally:
            os.unlink(path)
        if r.returncode != 0 or not r.stdout.strip():
            raise RuntimeError(f"{key}: rc={r.returncode} stderr={r.stderr.strip()[:400]}")
        return json.loads(r.stdout)

h = PSLocalRunner({"label": "ps-local", "host": "127.0.0.1", "port": 5985, "transport": "winrm-http", "username": "x"}, "x")
def keys(d): return sorted(d.keys()) if isinstance(d, dict) else type(d).__name__
def cmp(name, remote, local):
    same = keys(remote) == keys(local)
    print(f"{'OK ' if same else 'DIFF'} {name:<16} remote keys={keys(remote)}" + ("" if same else f"\n      local keys ={keys(local)}"))

t = time.time()
print("hello:", h.hello())
r = h.snapshot(); cmp("snapshot", r, LOCAL.snapshot()); print("     cpu:", r["cpu"], "| mem:", r["memory"]["percent"], "| top:", r["top_cpu_processes"][:2])
cmp("snapshot.cpu", r["cpu"], {k: 0 for k in ["percent","logical_cores","physical_cores","freq_mhz"]})
r = h.top_processes("memory", 3); cmp("top_processes", r, LOCAL.top_processes("memory", 3)); print("     ", r["processes"][:2])
r = h.disk_usage(); cmp("disk_usage", r, LOCAL.disk_usage()); print("     ", r["volumes"])
r = h.network_info(); cmp("network_info", r, LOCAL.network_info()); print("     ", r["throughput"], [i["name"] for i in r["interfaces"]][:4])
r = h.svc_lookup("wcncsvc"); cmp("svc_lookup", r, LOCAL.svc_lookup("wcncsvc")); print("     ", r)
print("     missing ->", h.svc_lookup("NoSuchSvc123"), "| quote-injection ->", h.svc_lookup("x' OR Name LIKE '%"))
r = h.svc_search("update", 3); print("     search:", [s["name"] for s in r])
r = h.svc_list("auto_stopped", 5); cmp("svc_list", r, LOCAL.svc_list("auto_stopped", 5)); print("     ", r["total_services_scanned"], "scanned,", [s["name"] for s in r["services"]])
print("     dependents(RpcSs):", (h.svc_dependents("RpcSs") or [])[:4], "| dependents(wcncsvc):", h.svc_dependents("wcncsvc"))
print("     sharing pid of wuauserv:", h.svc_sharing_pid((LOCAL.svc_lookup("wuauserv") or {}).get("pid") or 0)[:5])
print("control start:", h.svc_control("wcncsvc", "start"))
print("control start (noop):", h.svc_control("wcncsvc", "start"))
print("control restart:", h.svc_control("wcncsvc", "restart"))
print("control stop:", h.svc_control("wcncsvc", "stop"))
try: h.svc_control("Spooler", "stop")
except Exception as e: print("control stop Spooler (no admin) ->", type(e).__name__, e)
print("final wcncsvc:", LOCAL.svc_lookup("wcncsvc")["status"], f"| total {time.time()-t:.1f}s")
