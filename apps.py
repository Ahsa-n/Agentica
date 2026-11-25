"""
Application status monitoring — "is this configured application running and responsive?"

An application is registered once (name + machine + checks). Checks:
  process  : one or more process names must be running      (on the app's machine: local or WinRM)
  service  : a Windows / systemd service must be running     (on the app's machine)
  port     : a TCP port must accept connections              (from Agentica's PC, as a user sees it)
  url      : an HTTP(S) URL must answer with a status < 400  (from Agentica's PC)

Status:  up        every check passed
         degraded  running but not (fully) responsive: a port / URL fails, a window is
                   "Not responding" (desktop apps on this PC), or it answers slowly
         down      not running, or nothing responds
         unknown   nothing could be checked (machine unreachable / no credentials)
"""
from __future__ import annotations

import asyncio
import os
import re
import socket
import time
from datetime import datetime
from urllib.parse import urlparse

import httpx

APP_INTERVAL = 15.0     # seconds between background checks
PORT_TIMEOUT = 3.0
HTTP_TIMEOUT = 6.0
SLOW_MS = 3000          # a response slower than this counts as degraded

NAME_RE = re.compile(r"^[\w .()\-]{1,40}$")
PROC_RE = re.compile(r"^[\w .()\-]{1,60}$")
SVC_RE = re.compile(r"^[\w .@()\-]{1,80}$")


def validate(body: dict, machine_labels: list[str]) -> tuple[dict, list[str]]:
    """Operator input -> (fields, errors)."""
    errors = []
    name = str(body.get("name") or "").strip()
    if not NAME_RE.match(name):
        errors.append("Name: 1-40 letters, digits, spaces, dots, dashes or brackets.")
    machine = str(body.get("machine") or "").strip() or None
    if machine and machine.lower() in ("local", "this pc"):
        machine = None
    if machine and machine not in machine_labels:
        errors.append(f"Machine '{machine}' is not registered.")
    procs = [p.strip() for p in str(body.get("process") or "").split(",") if p.strip()]
    if len(procs) > 5 or any(not PROC_RE.match(p) for p in procs):
        errors.append("Process: up to 5 names separated by commas, e.g. nginx, php-cgi.")
    service = str(body.get("service") or "").strip() or None
    if service and not SVC_RE.match(service):
        errors.append("Service: use the service name, e.g. W3SVC or MSSQLSERVER.")
    port = body.get("port")
    if port in ("", None):
        port = None
    else:
        try:
            port = int(port)
            assert 1 <= port <= 65535
        except (ValueError, TypeError, AssertionError):
            errors.append("Port: a number between 1 and 65535.")
            port = None
    url = str(body.get("url") or "").strip() or None
    if url:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.netloc or len(url) > 300:
            errors.append("URL: must start with http:// or https://.")
    if not (procs or service or port or url) and not errors:
        errors.append("Add at least one check: a process, a service, a port or a URL.")
    return {"name": name, "machine": machine, "process": ", ".join(procs) or None, "service": service,
            "port": port, "url": url}, errors


class AppChecker:
    def __init__(self, store, registry, local_name: str) -> None:
        self.store = store
        self.registry = registry
        self.local_name = local_name
        self.status: dict[str, dict] = {}      # app id -> last background result
        self._last: dict[str, str | None] = {}  # app id -> last recorded status
        self._pids: dict[str, list[int]] = {}   # app id -> process ids at the last check (restart detection)
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ one app

    def _address(self, app: dict) -> str | None:
        if not app.get("machine"):
            return "127.0.0.1"
        m = self.store.machine_by_name(app["machine"])
        return m["host"] if m else None

    def check(self, app: dict) -> dict:
        """Run every configured check now (blocking)."""
        t_start = time.time()
        label = app.get("machine") or self.local_name
        checks: dict[str, dict] = {}
        host, host_err = self.registry.resolve(app.get("machine") or "local")

        if app.get("process"):
            names = [p.strip() for p in app["process"].split(",") if p.strip()]
            if host is None:
                checks["process"] = {"ok": None, "names": names, "error": str(host_err)}
            else:
                try:
                    r = host.processes_named(names)
                    checks["process"] = {"ok": r["count"] > 0, "names": names, **r}
                except Exception as e:  # noqa: BLE001
                    checks["process"] = {"ok": None, "names": names, "error": str(e)}

        if app.get("service"):
            if host is None:
                checks["service"] = {"ok": None, "name": app["service"], "error": str(host_err)}
            else:
                try:
                    info = host.svc_lookup(app["service"])
                    checks["service"] = {"ok": bool(info) and info["status"] == "running", "name": app["service"],
                                         "status": info["status"] if info else "not found"}
                except Exception as e:  # noqa: BLE001
                    checks["service"] = {"ok": None, "name": app["service"], "error": str(e)}

        addr = self._address(app)
        if app.get("port"):
            t0 = time.perf_counter()
            try:
                with socket.create_connection((addr, int(app["port"])), timeout=PORT_TIMEOUT):
                    pass
                checks["port"] = {"ok": True, "port": app["port"], "address": addr,
                                  "latency_ms": round((time.perf_counter() - t0) * 1000)}
            except OSError as e:
                if isinstance(e, socket.timeout):
                    why = "timed out"
                elif isinstance(e, ConnectionRefusedError) or getattr(e, "winerror", None) == 10061:
                    why = "connection refused"
                else:
                    why = e.strerror or str(e)
                checks["port"] = {"ok": False, "port": app["port"], "address": addr, "error": why}

        if app.get("url"):
            t0 = time.perf_counter()
            try:
                r = httpx.get(app["url"], timeout=HTTP_TIMEOUT, follow_redirects=True, verify=False)
                ms = round((time.perf_counter() - t0) * 1000)
                checks["http"] = {"ok": r.status_code < 400, "url": app["url"], "status": r.status_code,
                                  "latency_ms": ms, "slow": ms > SLOW_MS}
            except httpx.HTTPError as e:
                checks["http"] = {"ok": False, "url": app["url"],
                                  "error": "timed out" if isinstance(e, httpx.TimeoutException) else str(e) or type(e).__name__}

        status, summary = self._verdict(checks)
        return {"app": app["name"], "machine": label, "status": status, "summary": summary, "checks": checks,
                "checked": time.time(), "check_ms": round((time.time() - t_start) * 1000)}

    @staticmethod
    def _verdict(c: dict) -> tuple[str, str]:
        running = [c[k] for k in ("process", "service") if k in c]
        responsive = [c[k] for k in ("port", "http") if k in c]
        known = [x for x in running + responsive if x["ok"] is not None]
        if not known:
            why = next((x.get("error") for x in running + responsive if x.get("error")), "nothing could be checked")
            return "unknown", f"Could not check: {why}"

        def proc_txt():
            p = c.get("process")
            if not p or p["ok"] is None:
                return None
            n = ", ".join(p["names"])
            if not p["ok"]:
                return f"no '{n}' process running"
            usage = ""
            if p.get("memory_mb") is not None:
                mem = p["memory_mb"]
                usage = f" ({p.get('cpu_percent', 0):g}% CPU, {mem / 1024:.1f} GB)" if mem >= 1024 else f" ({p.get('cpu_percent', 0):g}% CPU, {mem:.0f} MB)"
            return f"{p['count']} '{n}' process{'es' if p['count'] != 1 else ''} running{usage}"

        down_parts = []
        if c.get("process", {}).get("ok") is False:
            down_parts.append(proc_txt())
        if c.get("service", {}).get("ok") is False:
            down_parts.append(f"service {c['service']['name']} is {c['service']['status']}")
        resp_ok = [x["ok"] for x in responsive if x["ok"] is not None]

        def resp_txt(x, kind):
            if kind == "port":
                return (f"port {x['port']} answers ({x['latency_ms']} ms)" if x["ok"]
                        else f"port {x['port']} does not answer ({x.get('error', 'refused')})")
            if x["ok"]:
                return f"{x['url']} returned {x['status']} in {x['latency_ms']} ms" + (" (slow)" if x.get("slow") else "")
            return f"{x['url']} failed ({x.get('error') or 'HTTP ' + str(x.get('status'))})"

        resp_parts = [resp_txt(c[k], k) for k in ("port", "http") if k in c and c[k]["ok"] is not None]

        if down_parts:
            return "down", "Not running: " + "; ".join(down_parts) + (". " + "; ".join(resp_parts) if resp_parts else "") + "."
        hung = (c.get("process") or {}).get("not_responding") or 0
        if hung:
            titles = ", ".join(f"'{t}'" for t in (c["process"].get("hung_windows") or [])[:2])
            return "degraded", (f"Running but frozen: {hung} window{'s' if hung > 1 else ''} not responding"
                                + (f" ({titles})" if titles else "") + "; " + (proc_txt() or "") + "."
                                + (" " + "; ".join(resp_parts) + "." if resp_parts else ""))
        if resp_ok and not any(resp_ok):
            run = [t for t in (proc_txt(),) if t] + ([f"service {c['service']['name']} is running"] if c.get("service", {}).get("ok") else [])
            if run:
                return "degraded", "Running but not responding: " + "; ".join(run + resp_parts) + "."
            return "down", "Not responding: " + "; ".join(resp_parts) + "."
        if resp_ok and not all(resp_ok):
            return "degraded", "Partly responding: " + "; ".join(resp_parts) + "."
        if c.get("http", {}).get("slow"):
            return "degraded", "Responding slowly: " + "; ".join(resp_parts) + "."
        parts = [t for t in (proc_txt(),) if t] + ([f"service {c['service']['name']} is running"] if c.get("service", {}).get("ok") else []) + resp_parts
        unknown = [k for k in c if c[k]["ok"] is None]
        tail = f" (could not check {', '.join(unknown)})" if unknown else ""
        return "up", "Up: " + "; ".join(parts) + tail + "."

    # ------------------------------------------------------------------ history

    def record(self, app: dict, res: dict) -> dict:
        """Store status changes and restarts; attach `since` + recent `history` to the result."""
        aid = app["id"]
        if aid not in self._last:
            ev = self.store.app_events(aid, limit=1)
            self._last[aid] = next((e["status"] for e in ev if e["status"] != "restarted"), None)
        pids = (res.get("checks", {}).get("process") or {}).get("pids")
        prev = self._pids.get(aid)
        if pids is not None:
            if prev and pids and not set(prev) & set(pids) and res["status"] in ("up", "degraded"):
                self.store.add_app_event(aid, "restarted", "All of its processes were replaced since the last check "
                                                           "(it crashed and came back, or was restarted).")
            self._pids[aid] = pids
        if res["status"] != self._last[aid]:
            self.store.add_app_event(aid, res["status"], res["summary"])
            self._last[aid] = res["status"]
        events = self.store.app_events(aid, limit=6)
        since = next((e["ts"] for e in events if e["status"] == res["status"]), None)
        res["since"] = since
        res["history"] = events
        return res

    @staticmethod
    def when(ts: float | None) -> str | None:
        if not ts:
            return None
        mins = int((time.time() - ts) // 60)
        ago = "just now" if mins < 1 else f"{mins} min ago" if mins < 120 else f"{mins // 60} h ago"
        return f"{datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')} ({ago})"

    # ------------------------------------------------------------------ for the agent tools

    def tool_status(self, name: str | None) -> dict:
        apps = self.store.apps()
        if not apps:
            return {"apps": [], "note": "No applications are configured. Ask to start monitoring one, or add it in the "
                                        "monitor panel (Applications > +)."}
        if name:
            q = name.strip().lower()
            hit = [a for a in apps if a["name"].lower() == q] or [a for a in apps if q in a["name"].lower()]
            if not hit:
                return {"apps": [], "error": f"No configured application matches '{name}'.",
                        "configured": [a["name"] for a in apps]}
            apps = hit
        out = []
        for a in apps:
            res = self.record(a, self.check(a))
            self.status[a["id"]] = res
            out.append({k: v for k, v in res.items() if k not in ("history", "since", "checked")} |
                       {"status_since": self.when(res["since"]),
                        "recent_changes": [{"at": self.when(e["ts"]), "status": e["status"], "summary": e["summary"]}
                                           for e in res["history"][:5]]})
        return {"apps": out}

    def find_app(self, query: str, host) -> dict | None:
        """A running (or, on this PC, installed) program matching `query` -> what to register."""
        import appfind
        q = query.strip().lower()

        def score(a):
            d, pr = a["display"].lower(), a["process"].lower()
            if q in (d, pr):
                return 100
            if d.startswith(q) or pr.startswith(q):
                return 85
            if appfind._tokens_match(q, d):
                return 78
            words = [w for w in re.findall(r"[a-z0-9]+", q) if len(w) >= 3]
            if pr in words or d in words:            # "ollama api" -> process "ollama"
                return 75
            if q in d:
                return 70
            return 0
        try:
            running = host.running_apps(include_background=True)
        except Exception:  # noqa: BLE001
            running = []
        best = max(running, key=score, default=None)
        if best and score(best) >= 70:
            return {"name": best["display"][:40], "process": best["process"], "ports": best.get("ports", []),
                    "running": True, "count": best.get("count")}
        if getattr(host, "is_local", False):
            inst, _ = appfind.find_installed(query)
            if inst and inst.get("exe"):
                return {"name": inst["name"][:40], "process": appfind._stem(os.path.basename(inst["exe"])),
                        "ports": [], "running": False}
        return None

    # ------------------------------------------------------------------ background monitor

    async def poll(self, app: dict) -> dict:
        try:
            res = await asyncio.wait_for(asyncio.to_thread(self.check, app), 45)
            res = await asyncio.to_thread(self.record, app, res)
        except Exception as e:  # noqa: BLE001
            res = {"app": app["name"], "machine": app.get("machine") or self.local_name, "status": "unknown",
                   "summary": f"Check failed: {e}", "checks": {}, "checked": time.time()}
        self.status[app["id"]] = res
        return res

    async def _loop(self) -> None:
        await asyncio.sleep(3)      # let the web server start listening first (apps may live on this PC)
        while True:
            started = time.monotonic()
            apps = await asyncio.to_thread(self.store.apps)
            for gone in set(self.status) - {a["id"] for a in apps}:
                self.status.pop(gone, None)
            if apps:
                await asyncio.gather(*(self.poll(a) for a in apps), return_exceptions=True)
            await asyncio.sleep(max(1.0, APP_INTERVAL - (time.monotonic() - started)))

    def view(self) -> dict:
        return {"interval": APP_INTERVAL,
                "apps": [{**a, "result": self.status.get(a["id"])} for a in self.store.apps()]}

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()


CHECKER: AppChecker | None = None      # set by server.py / tests via configure()


def configure(checker: AppChecker) -> None:
    global CHECKER
    CHECKER = checker
