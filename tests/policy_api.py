"""Policy engine over HTTP: allow / confirm / deny paths, approvals, rules, hot reload, audit.

    python server.py          (in another terminal)
    python tests/policy_api.py
"""
import httpx, json, time, shutil
from pathlib import Path
B = "http://127.0.0.1:8787"
P = Path(__file__).resolve().parents[1] / "policy.yaml"
c = httpx.Client(base_url=B, timeout=120)
SVC = "wcncsvc"
def call(tool, args, scope=["services"], target="localhost"):
    r = c.post(f"/api/tools/{tool}", json={"args": args, "scope": scope, "target": target, "session": "policytest"})
    return r.status_code, r.json()
def show(label, code, d):
    keep = {k: d[k] for k in ("decision", "risk", "summary", "error", "approval_id", "rule", "status") if k in d}
    if "result" in d and isinstance(d["result"], dict):
        keep["result"] = {k: d["result"][k] for k in ("action", "before", "after", "verified", "changed", "note") if k in d["result"]}
    print(f"{label:<34} [{code}] {json.dumps(keep)}")
    return d

print("--- baseline:", c.get(f"/api/tools/x").status_code if False else "", json.dumps(call("service_status", {"name": SVC})[1]["result"]["services"][0]))
show("read tool (R0)", *call("service_status", {"name": SVC}))
show("unregistered tool", *call("format_disk", {}))
show("out of scope", *call("service_start", {"name": SVC}, scope=["monitor"]))
show("invalid args (extra field)", *call("service_start", {"name": SVC, "force": True}))
show("invalid args (bad chars)", *call("service_start", {"name": "x;rm -rf"}))
show("unknown service", *call("service_start", {"name": "NoSuchSvc123"}))
show("hardline: stop RpcSs", *call("service_stop", {"name": "RpcSs"}))
d = show("restart WinRM (stopped -> start)", *call("service_restart", {"name": "WinRM"}))
if d.get("approval_id"): c.post(f"/api/approvals/{d['approval_id']}", json={"action": "deny"})
show("no-op: stop stopped svc", *call("service_stop", {"name": SVC}))
show("remote target (registered?)", *call("service_status", {"name": SVC}, target="10.9.9.9"))

def approve(aid, label="  approve"):
    r = c.post(f"/api/approvals/{aid}", json={"action": "approve"}); return show(label, r.status_code, r.json())
def deny(aid, label="  deny"):
    r = c.post(f"/api/approvals/{aid}", json={"action": "deny"}); return show(label, r.status_code, r.json())
def state(): return call("service_status", {"name": SVC})[1]["result"]["services"][0]["status"]

for p in c.get("/api/audit?limit=200").json()["entries"]:
    pass
d = show("start wcncsvc -> CONFIRM", *call("service_start", {"name": SVC}))
aid = d["approval_id"]
print("   approval record:", {k: v for k, v in c.get(f"/api/approvals/{aid}").json().items() if k in ("status", "args", "risk")})
approve(aid)
approve(aid, "  double approve")
print("   state now:", state())
show("hardline: stop RpcSs (running)", *call("service_stop", {"name": "RpcSs"}))
d = show("restart wcncsvc -> CONFIRM R2", *call("service_restart", {"name": SVC}))
approve(d["approval_id"])
d = show("stop wcncsvc -> CONFIRM R2", *call("service_stop", {"name": SVC}))
deny(d["approval_id"])
print("   state after deny:", state())
d = show("stop again -> CONFIRM R2", *call("service_stop", {"name": SVC}))
approve(d["approval_id"])
print("   state now:", state())

# per-target rule + hot reload
orig = P.read_text(encoding="utf-8")
try:
    P.write_text(orig.replace("rules: []", "rules:\n  - name: wcn test rule\n    tool: service_start\n    target: localhost\n    service: wcncsvc\n    decision: allow"), encoding="utf-8")
    time.sleep(0.1)
    show("rule allow start (no confirm)", *call("service_start", {"name": SVC}))
    d = show("rule does not cover stop", *call("service_stop", {"name": SVC}))
    if d.get("approval_id"): deny(d["approval_id"], "  (deny it)")
    P.write_text("defaults: [broken", encoding="utf-8"); time.sleep(0.1)
    print("   invalid yaml ->", c.get("/api/policy").json()["error"])
    d = show("invalid yaml -> safe defaults", *call("service_start", {"name": "MapsBroker"}))
    if d.get("approval_id"): deny(d["approval_id"], "  (deny it)")
finally:
    P.write_text(orig, encoding="utf-8")
time.sleep(0.1)
print("   restored policy error:", c.get("/api/policy").json()["error"])

# cleanup: put wcncsvc back to stopped
d = call("service_stop", {"name": SVC})[1]
if d.get("approval_id"): approve(d["approval_id"], "cleanup stop")
print("   final state:", state())
# access denied path (needs admin): start MapsBroker
d = show("start MapsBroker -> CONFIRM", *call("service_start", {"name": "MapsBroker"}))
if d.get("approval_id"):
    approve(d["approval_id"], "  approve (needs admin)")
print("\n--- audit (latest 8):")
for e in c.get("/api/audit?limit=8").json()["entries"]:
    print(f"  {e['tool']:<16} {e['risk']} {e['decision']:<9} {e['outcome']:<9} {(e['detail'] or '')[:70]}")
