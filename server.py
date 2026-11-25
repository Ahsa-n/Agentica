"""
Agentica — local web gateway.

Serves the web console, proxies chat to Ollama (streaming NDJSON), streams host
telemetry, and executes tools ONLY through the policy engine (policy.py).

    python server.py            -> http://127.0.0.1:8787
    python server.py --open     -> also opens the browser
    python server.py --host 0.0.0.0 --port 8787   (LAN access; no auth yet)

Controlling Windows services needs an elevated (Administrator) process.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import apps as appmon
import services
from agent import Agent, Busy
from fleet import FleetMonitor
from hosts import DEV, HostRegistry, RemoteError, delete_password, get_password, set_password
from machines import MAX_MACHINES, OS_DEFAULT_TRANSPORT, TRANSPORTS, Prober, parse_hosts
from actions import Actions
from policy import PolicyEngine
from router import Router
from store import Store
from telemetry import HOSTNAME, os_label, sampler, telemetry_payload
from tools import TOOLS, TOOLSETS

ROOT = Path(__file__).parent
OLLAMA = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434").rstrip("/")
STATIC_DIR = ROOT / "static"

store = Store()
prober = Prober(store)
registry = HostRegistry(store, port_state=lambda mid: prober.status.get(mid))
policy = PolicyEngine(ROOT / "policy.yaml", TOOLS, HOSTNAME, registry.resolve)
fleet = FleetMonitor(store, registry)
app_checker = appmon.AppChecker(store, registry, HOSTNAME)
appmon.configure(app_checker)
actions = Actions(store, policy)



def _app_phrases() -> dict[str, list[str]]:
    """Router examples for the monitored apps, so "is <app name> up" routes to Applications."""
    names = [a["name"] for a in store.apps()]
    return {"apps": [p.format(n) for n in names for p in ("is {} running", "is {} up", "check {}")]}


router = Router(TOOLSETS, OLLAMA, ROOT / "data" / "router_index.json", dynamic=_app_phrases)
agent = Agent(store=store, actions=actions, tools=TOOLS, toolsets=TOOLSETS, ollama_url=OLLAMA,
              local_name=HOSTNAME, os_label=os_label, checkpoint_path=ROOT / "data" / "checkpoints.db",
              router=router, routing=os.environ.get("AGENTICA_ROUTING", "embed"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    sampler.start()
    prober.start()
    fleet.start()
    app_checker.start()
    await agent.start()
    app.state.http = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0))
    yield
    sampler.stop()
    await prober.stop()
    await fleet.stop()
    await app_checker.stop()
    await agent.stop()
    await app.state.http.aclose()


app = FastAPI(title="Agentica", lifespan=lifespan)


# ============================================================ model gateway

@app.get("/api/health")
async def health():
    try:
        r = await app.state.http.get(f"{OLLAMA}/api/version", timeout=3)
        return {"ollama": True, "version": r.json().get("version"), "router": router.status()}
    except Exception as e:  # noqa: BLE001
        return {"ollama": False, "error": str(e), "router": router.status()}


@app.get("/api/models")
async def models():
    try:
        tags = (await app.state.http.get(f"{OLLAMA}/api/tags", timeout=5)).json()
        ps = (await app.state.http.get(f"{OLLAMA}/api/ps", timeout=5)).json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Ollama unreachable: {e}") from e
    loaded = {m["name"]: m for m in ps.get("models", [])}
    out = []
    for m in tags.get("models", []):
        if m.get("capabilities") == ["embedding"]:
            continue                       # embedding models (the router's) can't chat
        d = m.get("details", {})
        lm = loaded.get(m["name"])
        out.append({"name": m["name"], "size": m.get("size"), "family": d.get("family"),
                    "parameter_size": d.get("parameter_size"), "quantization": d.get("quantization_level"),
                    "context_length": d.get("context_length"), "capabilities": m.get("capabilities", []),
                    "loaded": bool(lm), "vram": lm.get("size_vram") if lm else None})
    return {"models": out}


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    client: httpx.AsyncClient = app.state.http

    async def relay():
        try:
            async with client.stream("POST", f"{OLLAMA}/api/chat", json=body) as r:
                if r.status_code != 200:
                    detail = (await r.aread()).decode(errors="replace")
                    try:
                        detail = json.loads(detail).get("error", detail)
                    except Exception:  # noqa: BLE001
                        pass
                    yield (json.dumps({"error": detail}) + "\n").encode()
                    return
                async for chunk in r.aiter_raw():
                    yield chunk
        except httpx.HTTPError as e:
            yield (json.dumps({"error": f"Ollama connection failed: {e}"}) + "\n").encode()

    return StreamingResponse(relay(), media_type="application/x-ndjson")


# ============================================================ telemetry

def _payload() -> dict:
    data = telemetry_payload()
    data["fleet"] = fleet.view()
    data["apps"] = app_checker.view()
    return data


@app.get("/api/telemetry")
def telemetry():
    return _payload()


@app.get("/api/telemetry/stream")
async def telemetry_stream(request: Request):
    """Server-Sent Events: one message per sampler tick (1 s)."""
    async def gen():
        last = -1
        yield "retry: 2000\n\n"
        while not await request.is_disconnected():
            if sampler.seq != last:
                last = sampler.seq
                data = await asyncio.to_thread(_payload)
                yield f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
            await asyncio.sleep(0.2)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ============================================================ tools + policy

@app.get("/api/tools")
def list_tools():
    return {"tools": [{"name": t.name, "risk": t.risk, "toolsets": t.toolsets, "schema": t.schema()}
                      for t in TOOLS.values()]}


@app.get("/api/router")
def router_status():
    """Stage 1 of the two-stage tool router: model, readiness, rules, how many requests it routed."""
    return {**router.status(), "default_mode": agent.routing}


@app.post("/api/router/route")
async def router_try(request: Request):
    """Body: {"text", "previous"?}. Shows what the router would load for a request (nothing is run)."""
    body = await request.json()
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Empty text")
    d = await router.route(text, previous=body.get("previous"), names=agent.machine_names(store.machines()))
    return {"domains": d.domains, "tools": [t.name for t in agent.tools_in(d.domains)], "scores": d.scores,
            "parts": d.parts, "context_used": d.context_used, "ms": d.ms, "error": d.error}


@app.get("/api/toolsets")
def list_toolsets():
    return {"toolsets": [{"id": i, **s, "card_only": s.get("card_only", False),
                          "tools": [n for n, t in TOOLS.items() if i in t.toolsets]}
                         for i, s in TOOLSETS.items()]}


@app.get("/api/policy")
def get_policy():
    return policy.summary()


@app.get("/api/audit")
def get_audit(limit: int = 100):
    return {"entries": store.audit_recent(max(1, min(limit, 1000)))}


@app.post("/api/tools/{name}")
async def run_tool(name: str, request: Request):
    """Body: {"args": {...}, "scope": [toolset ids] | null, "target": "<session target>", "session": "..."}

    Direct, policy-gated tool execution (used for testing / benchmarks; the agent uses the same Actions code)."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    body = body if isinstance(body, dict) else {}
    scope = body.get("scope") if isinstance(body.get("scope"), list) else None
    session = str(body.get("session") or "")[:64] or None
    payload, code = await actions.request(name, body.get("args"), scope, body.get("target"), session)
    return JSONResponse(payload, status_code=code)


def _approval_view(rec: dict) -> dict:
    return {k: rec[k] for k in ("id", "tool", "target", "args", "risk", "summary", "reasons", "status",
                                "created", "expires", "decided", "result")}


@app.get("/api/approvals/{aid}")
def get_approval(aid: str):
    rec = store.get_approval(aid)
    if not rec:
        raise HTTPException(404, "No such approval")
    return _approval_view(rec)


@app.post("/api/approvals/{aid}")
async def decide_approval(aid: str, request: Request):
    """Body: {"action": "approve" | "deny"}. Approval executes the stored, already-validated arguments."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    action = (body or {}).get("action")
    if action not in ("approve", "deny"):
        raise HTTPException(422, "action must be 'approve' or 'deny'")
    payload, code = await actions.decide(aid, action)
    if code == 404:
        raise HTTPException(404, "No such approval")
    return JSONResponse(payload, status_code=code)


# ============================================================ sessions (the agent runs server side)

def _session_or_404(sid: str) -> dict:
    s = agent.session_view(sid)
    if not s:
        raise HTTPException(404, "No such session")
    return s


@app.get("/api/sessions")
def list_sessions():
    return {"sessions": [agent.session_view(s["id"]) for s in store.sessions(limit=60)]}


@app.post("/api/sessions")
async def create_session(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    target = (body or {}).get("target") or None
    return agent.session_view(store.create_session(target)["id"])


@app.get("/api/sessions/{sid}")
async def get_session(sid: str):
    _session_or_404(sid)
    return await agent.view(sid)


@app.put("/api/sessions/{sid}")
async def update_session(sid: str, request: Request):
    _session_or_404(sid)
    body = await request.json()
    if "target" in body:
        store.update_session(sid, target=body["target"] or None)
    view = agent.session_view(sid)
    agent.emit(sid, "session", session=view)
    return view


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    _session_or_404(sid)
    try:
        await agent.delete(sid)
    except Busy as e:
        raise HTTPException(409, str(e)) from e
    return {"deleted": sid}


@app.post("/api/sessions/{sid}/messages")
async def post_message(sid: str, request: Request):
    """Body: {"text", "mode": "auto" | toolset id, "think": bool, "model", "routing"?: embed | llm | flat}.
    Runs in the background; watch /events."""
    _session_or_404(sid)
    body = await request.json()
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "Empty message")
    if not body.get("model"):
        raise HTTPException(422, "No model selected")
    try:
        item = await agent.send(sid, text, mode=str(body.get("mode") or "auto"), think=bool(body.get("think")),
                                model=str(body["model"]), routing=body.get("routing"))
    except Busy as e:
        raise HTTPException(409, str(e)) from e
    return JSONResponse({"item": item}, status_code=202)


@app.post("/api/sessions/{sid}/approval")
async def session_approval(sid: str, request: Request):
    """Body: {"action": "approve" | "deny"} — resumes the paused run."""
    _session_or_404(sid)
    action = (await request.json()).get("action")
    if action not in ("approve", "deny"):
        raise HTTPException(422, "action must be 'approve' or 'deny'")
    try:
        await agent.decide(sid, action)
    except KeyError as e:
        raise HTTPException(409, str(e)) from e
    return {"ok": True}


@app.post("/api/sessions/{sid}/cancel")
async def session_cancel(sid: str):
    _session_or_404(sid)
    await agent.cancel(sid)
    return {"ok": True}


@app.get("/api/sessions/{sid}/events")
async def session_events(sid: str, request: Request):
    """SSE: a snapshot first, then live events (seq-ordered; events already in the snapshot are skipped)."""
    _session_or_404(sid)
    q = agent.bus.subscribe(sid)

    async def gen():
        try:
            snap = await agent.view(sid)
            yield f"data: {json.dumps({'type': 'snapshot', **snap}, separators=(',', ':'))}\n\n"
            seen = snap["seq"]
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if ev["seq"] <= seen:
                    continue
                seen = ev["seq"]
                yield f"data: {json.dumps(ev, separators=(',', ':'))}\n\n"
        finally:
            agent.bus.unsubscribe(sid, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ============================================================ applications (status monitoring)

def _app_fields(body: dict) -> dict:
    fields, errors = appmon.validate(body or {}, [m["label"] for m in store.machines()])
    if errors:
        raise HTTPException(422, " ".join(errors))
    return fields


@app.get("/api/apps")
def list_apps():
    return app_checker.view()


@app.post("/api/apps")
async def add_app(request: Request):
    f = _app_fields(await request.json())
    a = store.add_app(**f)
    if a is None:
        raise HTTPException(409, f"An application named '{f['name']}' already exists.")
    return {**a, "result": await app_checker.poll(a)}


@app.put("/api/apps/{aid}")
async def edit_app(aid: str, request: Request):
    if not store.app(aid):
        raise HTTPException(404, "No such application")
    f = _app_fields(await request.json())
    a = store.update_app(aid, **f)
    if a is None:
        raise HTTPException(409, f"An application named '{f['name']}' already exists.")
    return {**a, "result": await app_checker.poll(a)}


@app.get("/api/apps/discover")
async def discover_apps(machine: str | None = None, background: bool = False):
    """Running programs on a machine (friendly name, process, count, memory, ports) for the Add dialog's picker."""
    host, err = registry.resolve(machine or "local")
    if host is None:
        raise HTTPException(409, str(err))
    try:
        found = await asyncio.wait_for(asyncio.to_thread(host.running_apps, background), 45)
    except (RemoteError, asyncio.TimeoutError) as e:
        raise HTTPException(502, str(e) or "The machine did not answer in time.") from e
    return {"machine": host.label, "apps": found}


@app.post("/api/apps/{aid}/check")
async def check_app(aid: str):
    a = store.app(aid)
    if not a:
        raise HTTPException(404, "No such application")
    return {**a, "result": await app_checker.poll(a)}


@app.delete("/api/apps/{aid}")
def delete_app(aid: str):
    if not store.delete_app(aid):
        raise HTTPException(404, "No such application")
    app_checker.status.pop(aid, None)
    return {"deleted": aid}


# ============================================================ machine registry

def _machine_view(m: dict) -> dict:
    return {**m, "has_credentials": bool(m.get("username")) and get_password(m["id"]) is not None,
            "status": prober.status.get(m["id"], {"state": "unknown"})}


@app.get("/api/machines")
def list_machines():
    return {"local": {"id": "local", "label": "This PC", "host": HOSTNAME, "os": "windows" if services.IS_WINDOWS else "linux"},
            "machines": [_machine_view(m) for m in store.machines()]}


async def _test_machine(m: dict) -> dict:
    """Explicit connection test: re-probe the port, then really try to sign in (ignores cached probe results)."""
    probe = await prober.probe(m)
    if probe["state"] == "unreachable":
        msg = f"{m['label']} ({m['host']}) port {m['port']} is not reachable ({probe.get('error') or 'no response'}). "               "Is the machine on, and was Enable-AgenticaTarget.ps1 run on it?"
        store.record_test(m["id"], False, error=msg)
        return {"ok": False, "error": msg}
    host, err = registry.for_machine(m, use_probe=False)
    if host is None:
        return {"ok": False, "error": str(err)}
    try:
        info = await asyncio.wait_for(asyncio.to_thread(host.hello), 45)
        store.record_test(m["id"], True, info=info)
        return {"ok": True, "info": info}
    except (RemoteError, asyncio.TimeoutError) as e:
        msg = str(e) or f"{m['label']} did not respond in time."
        store.record_test(m["id"], False, error=msg)
        return {"ok": False, "error": msg}


@app.post("/api/machines")
async def add_machines(request: Request):
    """Body: {"hosts": "10.0.0.5, web-01:5985 ...", "os", "transport", "label", "username", "password"}"""
    body = await request.json()
    os_ = str(body.get("os", "windows")).lower()
    if os_ not in OS_DEFAULT_TRANSPORT:
        raise HTTPException(422, "os must be 'windows' or 'linux'")
    transport = str(body.get("transport") or OS_DEFAULT_TRANSPORT[os_])
    if transport not in TRANSPORTS or (os_ == "linux") != (transport == "ssh"):
        raise HTTPException(422, f"transport '{transport}' does not fit os '{os_}'")
    valid, invalid = parse_hosts(str(body.get("hosts", ""))[:5000])
    if not valid and not invalid:
        raise HTTPException(422, "Enter at least one IP address or hostname")
    label = str(body.get("label") or "").strip()[:40]
    username = str(body.get("username") or "").strip()[:128] or None
    password = body.get("password") or None
    existing = len(store.machines())
    added, duplicates = [], []
    for host, port in valid:
        if existing + len(added) >= MAX_MACHINES:
            invalid.append(f"{host} (limit of {MAX_MACHINES} machines reached)")
            continue
        if host.lower() in ("localhost", "127.0.0.1", "::1", HOSTNAME.lower()):
            duplicates.append(host)
            continue
        m = store.add_machine(label=label if label and len(valid) == 1 else host, host=host, os=os_,
                              transport=transport, port=port or TRANSPORTS[transport],
                              username=username if password else None)
        if m is None:
            duplicates.append(host)
            continue
        if username and password:
            set_password(m["id"], str(password))
        added.append(m)
    if added:
        await asyncio.gather(*(prober.probe(m) for m in added))
        if username and password:
            await asyncio.gather(*(_test_machine(m) for m in added))
        for m in added:
            asyncio.create_task(fleet.poll(store.machine(m["id"])))
    return {"added": [_machine_view(store.machine(m["id"])) for m in added], "duplicates": duplicates, "invalid": invalid}


@app.put("/api/machines/{mid}/credentials")
async def set_credentials(mid: str, request: Request):
    """Body: {"username": "...", "password": "..."} — the password goes to the OS keyring. Then tests the connection."""
    m = store.machine(mid)
    if not m:
        raise HTTPException(404, "No such machine")
    body = await request.json()
    username = str(body.get("username") or "").strip()[:128]
    password = body.get("password")
    if not username or not password:
        raise HTTPException(422, "Username and password are required")
    set_password(mid, str(password))
    store.set_machine_username(mid, username)
    registry.forget(mid)
    result = await _test_machine(store.machine(mid))
    asyncio.create_task(fleet.poll(store.machine(mid)))
    return {**result, "machine": _machine_view(store.machine(mid))}


@app.post("/api/machines/{mid}/test")
async def test_machine(mid: str):
    m = store.machine(mid)
    if not m:
        raise HTTPException(404, "No such machine")
    result = await _test_machine(m)
    return {**result, "machine": _machine_view(store.machine(mid))}


@app.delete("/api/machines/{mid}")
def delete_machine(mid: str):
    if not store.delete_machine(mid):
        raise HTTPException(404, "No such machine")
    registry.forget(mid)
    delete_password(mid)
    prober.status.pop(mid, None)
    return {"deleted": mid}


# ============================================================ static UI

class NoCacheStatic(StaticFiles):
    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/", NoCacheStatic(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser(description="Agentica web console")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--open", action="store_true", help="open the browser on start")
    a = ap.parse_args()
    url = f"http://{'127.0.0.1' if a.host in ('0.0.0.0', '::') else a.host}:{a.port}"
    print(f"\n  AGENTICA  ->  {url}\n  ollama    ->  {OLLAMA}\n  policy    ->  {policy.path}"
          + ("\n  dev mode  ->  'local-ps' loopback transport enabled" if DEV else "")
          + (f"  (!) {policy.error}" if policy.error else "") + "\n")
    if a.open:
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning", timeout_graceful_shutdown=1)
