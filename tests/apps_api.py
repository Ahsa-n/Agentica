"""Application status monitoring over HTTP: up / down / degraded verdicts, validation, the app_status tool.

    python server.py          (in another terminal)
    python tests/apps_api.py

Creates apps named test-* and removes them afterwards.
"""
import httpx, json
c = httpx.Client(base_url="http://127.0.0.1:8787", timeout=60)
TEST_PREFIX = "test-"
for a in c.get("/api/apps").json()["apps"]:
    if a["name"].startswith(TEST_PREFIX): c.delete(f"/api/apps/{a['id']}")
cases = [
    ("test-agentica-web", dict(process="python", port=8787, url="http://127.0.0.1:8787/api/health"), "up"),
    ("test-ghost-app", dict(process="nonexistent-proc", port=59999), "down"),
    ("test-half-app", dict(process="python", port=59998), "degraded"),
    ("test-half-url", dict(port=8787, url="http://127.0.0.1:8787/does-not-exist-404"), "degraded"),
    ("test-wcn-stopped", dict(service="wcncsvc"), "down"),
    ("test-dns-client", dict(service="Dnscache", process="svchost"), "up"),
]
for name, f, expect in cases:
    r = c.post("/api/apps", json={"name": name, **f}).json()
    res = r["result"]
    print(f"{'OK ' if res['status'] == expect else 'BAD'} {name:<18} -> {res['status']:<9} {res['summary'][:120]}")
print("--- validation")
for body in [{"name": "x"}, {"name": "x", "url": "ftp://a"}, {"name": "x", "port": 70000}, {"name": "x", "process": "a;b"},
             {"name": "x", "port": 80, "machine": "nope"}, {"name": "test-agentica-web", "port": 80}, {"name": "bad/name", "port": 80}]:
    r = c.post("/api/apps", json=body); print(r.status_code, r.json()["detail"][:110])
print("--- tool through the policy engine")
r = c.post("/api/tools/app_status", json={"args": {"name": "test-agentica"}, "scope": ["apps"]}).json()
print(r["decision"], r["risk"], "|", [(a["app"], a["status"]) for a in r["result"]["apps"]], "| machine:", r["result"]["machine"])
r = c.post("/api/tools/app_status", json={"args": {}, "scope": ["apps"], "target": "some-unknown-box"}).json()
print("ignores session target:", r["decision"], len(r["result"]["apps"]), "apps")
r = c.post("/api/tools/app_status", json={"args": {"name": "zzz"}, "scope": ["apps"]}).json()
print("no match:", r["result"])
print("--- monitor view")
v = c.get("/api/telemetry").json()["apps"]
print("interval", v["interval"], [(a["name"], (a["result"] or {}).get("status")) for a in v["apps"]])
print("toolsets:", [t["id"] for t in c.get("/api/toolsets").json()["toolsets"]])

print("--- cleanup")
for a in c.get("/api/apps").json()["apps"]:
    if a["name"].startswith(TEST_PREFIX): c.delete(f"/api/apps/{a['id']}")
print("test apps removed")

print("--- open / register tools (approval requested, then DENIED so nothing opens or changes)")
def tool(name, args):
    return c.post(f"/api/tools/{name}", json={"args": args, "scope": ["apps"], "session": "apps-test"}).json()
r = tool("app_open", {"name": "calc"})
print("OK " if r["decision"] == "CONFIRM" and "Calculator" in r["summary"] else "BAD", "app_open asks first:", r["summary"])
if r.get("approval_id"):
    c.post(f"/api/approvals/{r['approval_id']}", json={"action": "deny"})
r = tool("app_open", {"name": "zzzz-not-installed"})
print("OK " if r["decision"] == "DENY" else "BAD", "unknown app refused:", r.get("error"))
r = tool("app_register", {"name": "zzzz-not-running"})
print("OK " if r["decision"] == "DENY" else "BAD", "unknown app not registered:", r.get("error"))
