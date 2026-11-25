"""
Tool registry. Each tool has:
  - a strict Pydantic argument model (also used to generate the schema the model sees),
  - a base risk tier and the toolsets (task cards) it belongs to,
  - `run(args, host)` — executes on a host (this PC or a remote machine, see hosts.py),
  - optionally `assess(args, host)` — grades the *concrete* call against the target's live state.
Tools never decide whether they may run — the policy engine does.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

import os

import psutil

import appfind
import apps as appmon
import services
from policy import Assessment


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoArgs(Args):
    pass


class TopProcessesArgs(Args):
    sort_by: Literal["cpu", "memory"] = Field("cpu", description="Sort key")
    limit: int = Field(10, ge=1, le=25, description="How many processes (1-25)")


class ServiceQueryArgs(Args):
    name: str = Field(..., min_length=1, max_length=80,
                      description="Service name or part of its display name, e.g. 'wuauserv' or 'Update'")


class ListServicesArgs(Args):
    filter: Literal["auto_stopped", "running", "stopped", "all"] = Field(
        "auto_stopped", description="Which services to list")
    limit: int = Field(40, ge=1, le=80, description="Max services to return (1-80)")


class AppStatusArgs(Args):
    name: str | None = Field(None, max_length=40,
                             description="Name (or part of the name) of a configured application. Omit to check all of them.")


class AppOpenArgs(Args):
    name: str = Field(..., min_length=1, max_length=60,
                      description="The app to open, as the operator said it, e.g. 'VS Code', 'Calculator', 'Edge'.")


class AppRegisterArgs(Args):
    name: str = Field(..., min_length=1, max_length=60,
                      description="The app to start monitoring, e.g. 'VS Code' or 'SQL Server'.")
    port: int | None = Field(None, ge=1, le=65535, description="Optional TCP port that must answer")
    url: str | None = Field(None, max_length=300, description="Optional http(s) URL that must answer")


class ServiceArgs(Args):
    name: str = Field(..., min_length=1, max_length=80, pattern=r"^[\w .@()\-]+$",
                      description="Exact service name (not the display name), e.g. 'Spooler'. "
                                  "Use service_status first if you only know the display name.")


def _strip_titles(node):
    if isinstance(node, dict):
        return {k: _strip_titles(v) for k, v in node.items() if k != "title"}
    if isinstance(node, list):
        return [_strip_titles(v) for v in node]
    return node


@dataclass
class Tool:
    name: str
    description: str
    Args: type[Args]
    run: Callable[[Args, object], dict]
    risk: str
    toolsets: list[str]
    assess: Callable[[Args, object], Assessment] | None = None
    uses_target: bool = True      # False: the tool knows where it runs (e.g. each app has its own machine)

    def schema(self) -> dict:
        params = _strip_titles(self.Args.model_json_schema())
        params.setdefault("properties", {})
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": params}}


# --------------------------------------------------------------------------- read-only

def app_status(a: AppStatusArgs, _host) -> dict:
    if appmon.CHECKER is None:
        return {"apps": [], "error": "Application monitoring is not running."}
    return appmon.CHECKER.tool_status(a.name)


def service_status(a: ServiceQueryArgs, host) -> dict:
    exact = host.svc_lookup(a.name.strip())
    if exact:
        return {"match": "exact", "services": [exact]}
    return {"match": "search", "query": a.name, "services": host.svc_search(a.name.strip())}


# --------------------------------------------------------------------------- applications: open / register

def _assess_open(a: AppOpenArgs, host) -> Assessment:
    summary = f"Open '{a.name}' on {host.label}"
    if not host.is_local:
        return Assessment("R1", summary, error=f"Desktop apps can only be opened on this PC: a program started remotely on "
                                               f"{host.label} would not appear on anyone's screen.")
    if not appfind.IS_WINDOWS:
        return Assessment("R1", summary, error="Opening apps is only supported on Windows.")
    app, cands = appfind.find_installed(a.name)
    if not app:
        close = ", ".join(c["name"] for c in cands[:3])
        return Assessment("R1", summary, blocked_by="request",
                          error=f"No installed app matches '{a.name}'." + (f" Closest: {close}." if close else ""))
    reasons = ["starts a program on your desktop (reversible: you can close it any time)"]
    if app.get("exe"):
        stem = appfind._stem(os.path.basename(app["exe"])).lower()
        if any(appfind._stem(n).lower() == stem for n in (p.name() for p in psutil.process_iter())):
            reasons.append("it is already running; Windows will open another window or bring it to the front")
    return Assessment("R1", f"Open '{app['name']}' on {host.label}", reasons=reasons)


def app_open(a: AppOpenArgs, _host) -> dict:
    app, _ = appfind.find_installed(a.name)
    if not app:
        raise services.ServiceError(f"No installed app matches '{a.name}'.")
    return appfind.launch(app)


def _register_plan(a: AppRegisterArgs, host):
    ck = appmon.CHECKER
    if ck is None:
        return None, "Application monitoring is not running."
    q = a.name.strip().lower()
    for x in ck.store.apps():                     # asked by the name it is already monitored under?
        n = x["name"].lower()
        if n == q or (len(q) >= 4 and (q in n or n in q)):
            return None, f"'{x['name']}' is already being monitored."
    found = ck.find_app(a.name, host)
    if not found:
        return None, (f"Could not find a running{' or installed' if host.is_local else ''} app matching '{a.name}' "
                      f"on {host.label}.")
    machine = None if host.is_local else host.label
    for x in ck.store.apps():
        if x["name"].lower() == found["name"].lower():
            return None, f"'{x['name']}' is already being monitored."
        if (x["machine"] or None) == machine and (x["process"] or "").lower() == found["process"].lower():
            return None, (f"'{x['name']}' already monitors the {found['process']} process on {host.label}; "
                          "edit that application instead of adding a second one.")
    fields, errors = appmon.validate({"name": found["name"], "machine": machine, "process": found["process"],
                                      "port": a.port, "url": a.url}, [m["label"] for m in ck.store.machines()])
    if errors:
        return None, " ".join(errors)
    return {**fields, "_found": found}, None


def _assess_register(a: AppRegisterArgs, host) -> Assessment:
    plan, err = _register_plan(a, host)
    if err:
        kind = "state" if "already being monitored" in err else "request"
        return Assessment("R1", f"Start monitoring '{a.name}' on {host.label}", error=err, blocked_by=kind)
    f = plan["_found"]
    checks = [f"process {plan['process']}"] + ([f"port {plan['port']}"] if plan["port"] else []) + ([plan["url"]] if plan["url"] else [])
    reasons = ["adds it to the monitored applications (reversible: you can remove it any time)"]
    if not f["running"]:
        reasons.append("it is not running right now, so it will show as down until started")
    if f.get("ports") and not plan["port"]:
        reasons.append(f"it listens on port(s) {', '.join(map(str, f['ports'][:4]))}; a port check can be added later")
    return Assessment("R1", f"Start monitoring '{plan['name']}' ({', '.join(checks)}) on {host.label}", reasons=reasons)


def app_register(a: AppRegisterArgs, host) -> dict:
    plan, err = _register_plan(a, host)
    if err:
        raise services.ServiceError(err)
    found = plan.pop("_found")
    ck = appmon.CHECKER
    app = ck.store.add_app(**plan)
    if app is None:
        raise services.ServiceError(f"An application named '{plan['name']}' already exists.")
    res = ck.record(app, ck.check(app))
    ck.status[app["id"]] = res
    return {"registered": app["name"], "process": app["process"], "port": app["port"], "url": app["url"],
            "suggested_ports": found.get("ports", [])[:6], "status": res["status"], "summary": res["summary"]}


# --------------------------------------------------------------------------- service control

VERB = {"start": "Start", "stop": "Stop", "restart": "Restart"}


def _assess_service(action: str) -> Callable[[ServiceArgs, object], Assessment]:
    def assess(a: ServiceArgs, host) -> Assessment:
        target = host.label
        info = host.svc_lookup(a.name)
        if info is None:
            return Assessment("R2", f"{VERB[action]} service '{a.name}' on {target}", service=a.name,
                              blocked_by="request",
                              error=f"No service named '{a.name}' on {target}. Use service_status to search by "
                                    "display name, then pass the exact service name.")
        name, disp, st = info["name"], info.get("display_name") or info["name"], info["status"]
        label = f"'{disp}' ({name})" if disp and disp.lower() != name.lower() else f"'{name}'"
        summary = f"{VERB[action]} service {label} on {target}"
        base = dict(summary=summary, service=name)

        if action == "start" or (action == "restart" and st != "running"):
            if st == "running":
                return Assessment("R0", reasons=["already running, so nothing will change"], noop=True, **base)
            if info.get("start_type") == "disabled":
                return Assessment("R2", error="The service is disabled. Changing a service's startup type is not "
                                              "supported; enable it manually first.", **base)
            why = "starts a stopped service (reversible)"
            if action == "restart":
                why = "the service is not running, so a restart only starts it (reversible)"
            return Assessment("R1", reasons=[why], **base)

        if action == "stop" and st == "stopped":
            return Assessment("R0", reasons=["already stopped, so nothing will change"], noop=True, **base)
        deps = host.svc_dependents(name)
        if deps:
            shown = ", ".join(deps[:5]) + ("…" if len(deps) > 5 else "")
            return Assessment("R2", error=f"{len(deps)} running service(s) depend on it ({shown}). "
                                          "Stop those first.", stops_service=True, **base)
        reasons = ["stops a running service; anything using it is interrupted"]
        if action == "restart":
            reasons = ["briefly stops a running service, then starts it again"]
        if info.get("pid"):
            sharing = [s for s in host.svc_sharing_pid(info["pid"]) if s.lower() != name.lower()]
            if sharing:
                reasons.append(f"shares a host process with {len(sharing)} other service(s)")
        if not host.is_local:
            reasons.append(f"runs on the remote machine {target}")
        return Assessment("R2", reasons=reasons, stops_service=True, **base)
    return assess


# --------------------------------------------------------------------------- registry

_T = [
    Tool("system_snapshot", "Live health snapshot of the target machine: CPU %, cores, memory, swap, uptime and the "
         "busiest processes.", NoArgs, lambda a, h: h.snapshot(), "R0", ["monitor", "troubleshoot"]),
    Tool("top_processes", "List the top processes on the target machine sorted by CPU or memory usage.",
         TopProcessesArgs, lambda a, h: h.top_processes(a.sort_by, a.limit), "R0", ["monitor", "troubleshoot"]),
    Tool("disk_usage", "Capacity, used and free space for every volume on the target machine.",
         NoArgs, lambda a, h: h.disk_usage(), "R0", ["storage", "troubleshoot"]),
    Tool("service_status", "Look up one system service (Windows SCM or systemd) by exact name or partial display "
         "name. Returns name, display name, status, start type and PID.",
         ServiceQueryArgs, service_status, "R0", ["services", "troubleshoot"]),
    Tool("list_services", "List system services by state. 'auto_stopped' = set to start automatically but not "
         "running (likely problems).", ListServicesArgs, lambda a, h: h.svc_list(a.filter, a.limit), "R0",
         ["services", "troubleshoot"]),
    Tool("network_info", "Network interfaces, IPv4 addresses, link speed and current throughput of the target "
         "machine.", NoArgs, lambda a, h: h.network_info(), "R0", ["network", "troubleshoot"]),
    Tool("app_status", "Check whether configured applications are running and responsive: their processes / "
         "service on their own machine, and their TCP port / URL as a user would reach them. Returns status "
         "up / degraded / down / unknown with evidence for each check.", AppStatusArgs, app_status, "R0",
         ["apps", "troubleshoot"], uses_target=False),
    Tool("app_open", "Open (launch) an installed app on this PC by name, e.g. 'VS Code', 'Calculator', 'Edge'. Any "
         "installed app can be opened; it does not need to be monitored. The operator is asked to approve first. "
         "Reports whether a window / process actually appeared.", AppOpenArgs, app_open, "R1", ["apps"], _assess_open),
    Tool("app_register", "Start monitoring an application: finds it by name among running (or installed) programs on "
         "the target machine and adds it with a process check, plus an optional port / URL check. The operator is "
         "asked to approve first.", AppRegisterArgs, app_register, "R1", ["apps"], _assess_register),
    Tool("service_start", "Start a stopped service and verify it is running. Goes through the policy engine; "
         "the operator may be asked to approve it.", ServiceArgs, lambda a, h: h.svc_control(a.name, "start"),
         "R1", ["services"], _assess_service("start")),
    Tool("service_stop", "Stop a running service and verify it stopped. Goes through the policy engine; the "
         "operator may be asked to approve it.", ServiceArgs, lambda a, h: h.svc_control(a.name, "stop"),
         "R2", ["services"], _assess_service("stop")),
    Tool("service_restart", "Restart a service (stop, then start) and verify it is running. Goes through the "
         "policy engine; the operator may be asked to approve it.", ServiceArgs,
         lambda a, h: h.svc_control(a.name, "restart"), "R2", ["services"], _assess_service("restart")),
]
TOOLS: dict[str, Tool] = {t.name: t for t in _T}

# Task cards. `default` runs automatically when a card-scoped turn would otherwise end
# without any tool call. `card_only` toolsets cannot be loaded on demand in Auto mode.
# Troubleshoot is deliberately read-only: it diagnoses; changes happen from the Services card.
TOOLSETS: dict[str, dict] = {
    "monitor": {"name": "Monitoring", "desc": "CPU, memory, processes, uptime",
                "default": {"name": "system_snapshot", "args": {}}},
    "storage": {"name": "Storage", "desc": "volumes, capacity, free space",
                "default": {"name": "disk_usage", "args": {}}},
    "services": {"name": "Services", "desc": "service status, start, stop, restart (Windows SCM / systemd)",
                 "default": {"name": "list_services", "args": {"filter": "auto_stopped"}}},
    "network": {"name": "Network", "desc": "interfaces, addresses, throughput",
                "default": {"name": "network_info", "args": {}}},
    "apps": {"name": "Applications", "desc": "application status, open installed apps, start monitoring an app",
             "default": {"name": "app_status", "args": {}}},
    "troubleshoot": {"name": "Troubleshoot", "desc": "read-only, evidence-first diagnosis across every domain",
                     "default": {"name": "system_snapshot", "args": {}}, "card_only": True},
}
