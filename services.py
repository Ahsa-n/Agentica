"""
System services — lookup, listing and *verified* control.

Windows: psutil (read) + pywin32 / Service Control Manager (control).
Linux:   systemctl (read and control). Names go in as argv items, never through a shell.

Every control action re-reads the service state afterwards and reports whether
the service actually reached the expected state (`verified`).
"""
from __future__ import annotations

import platform
import subprocess
import time

import psutil

IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    import pywintypes
    import win32service
    import win32serviceutil

WAIT_S = 25          # how long to wait for a state change before reporting "not verified"
POLL_S = 0.25


class ServiceError(Exception):
    """A control action failed; the message is safe to show to the operator and the model."""


# --------------------------------------------------------------------------- read

WIN_STATE = {1: "stopped", 2: "start_pending", 3: "stop_pending", 4: "running",
             5: "continue_pending", 6: "pause_pending", 7: "paused"}


def _win_info(svc) -> dict:
    d = svc.as_dict()
    return {"name": d.get("name"), "display_name": d.get("display_name"), "status": d.get("status"),
            "start_type": d.get("start_type"), "pid": d.get("pid")}


def _systemctl_show(name: str) -> dict:
    res = subprocess.run(
        ["systemctl", "show", name, "--no-pager",
         "--property=Id,Description,LoadState,ActiveState,SubState,UnitFileState,MainPID"],
        capture_output=True, text=True, timeout=8,
    )
    return dict(line.split("=", 1) for line in res.stdout.splitlines() if "=" in line)


_LINUX_STATE = {"active": "running", "inactive": "stopped", "failed": "failed",
                "activating": "start_pending", "deactivating": "stop_pending", "reloading": "running"}
_LINUX_START = {"enabled": "automatic", "enabled-runtime": "automatic", "disabled": "disabled",
                "masked": "disabled", "static": "manual", "indirect": "manual", "generated": "automatic"}


def lookup(name: str) -> dict | None:
    """Exact service by name. None if it does not exist."""
    if IS_WINDOWS:
        try:
            return _win_info(psutil.win_service_get(name))
        except (psutil.NoSuchProcess, OSError, ValueError):
            return None
    props = _systemctl_show(name)
    if not props or props.get("LoadState") in ("not-found", None):
        return None
    pid = int(props.get("MainPID") or 0)
    return {"name": props.get("Id", name), "display_name": props.get("Description", ""),
            "status": _LINUX_STATE.get(props.get("ActiveState", ""), props.get("ActiveState")),
            "start_type": _LINUX_START.get(props.get("UnitFileState", ""), props.get("UnitFileState")),
            "pid": pid or None, "sub_state": props.get("SubState")}


def search(query: str, limit: int = 8) -> list[dict]:
    q = query.lower()
    out = []
    if IS_WINDOWS:
        for s in psutil.win_service_iter():
            try:
                if q in s.name().lower() or q in s.display_name().lower():
                    out.append(_win_info(s))
            except Exception:  # noqa: BLE001 - services can vanish mid-iteration
                continue
            if len(out) >= limit:
                break
        return out
    res = subprocess.run(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain", "--no-pager"],
                         capture_output=True, text=True, timeout=8)
    for line in res.stdout.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 4 and (q in parts[0].lower() or (len(parts) > 4 and q in parts[4].lower())):
            info = lookup(parts[0])
            if info:
                out.append(info)
            if len(out) >= limit:
                break
    return out


def list_services(filt: str, limit: int) -> dict:
    out, total = [], 0
    if IS_WINDOWS:
        for s in psutil.win_service_iter():
            try:
                d = _win_info(s)
            except Exception:  # noqa: BLE001
                continue
            total += 1
            running = d["status"] == "running"
            keep = (filt == "all" or (filt == "running" and running) or (filt == "stopped" and not running)
                    or (filt == "auto_stopped" and not running and d["start_type"] == "automatic"))
            if keep and len(out) < limit:
                out.append(d)
    else:
        state = {"auto_stopped": "failed", "running": "running", "stopped": "inactive", "all": None}[filt]
        cmd = ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain", "--no-pager"]
        if state:
            cmd.append(f"--state={state}")
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        for line in res.stdout.splitlines():
            parts = line.split(None, 4)
            if len(parts) >= 4:
                total += 1
                if len(out) < limit:
                    out.append({"name": parts[0], "status": _LINUX_STATE.get(parts[2], parts[2]),
                                "sub_state": parts[3], "display_name": parts[4] if len(parts) > 4 else ""})
    result = {"filter": filt, "total_services_scanned": total, "matched": len(out), "services": out}
    if filt == "auto_stopped":
        result["note"] = ("Automatic services that are stopped are not always faults: delayed-start and "
                          "trigger-start services stop on their own when idle.")
    return result


def running_dependents(name: str) -> list[str] | None:
    """Services that depend on `name` and are running. None if this cannot be determined."""
    if IS_WINDOWS:
        try:
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
            try:
                hs = win32service.OpenService(scm, name, win32service.SERVICE_ENUMERATE_DEPENDENTS)
                try:
                    deps = win32service.EnumDependentServices(hs, win32service.SERVICE_ACTIVE)
                finally:
                    win32service.CloseServiceHandle(hs)
            finally:
                win32service.CloseServiceHandle(scm)
            return [d[0] for d in deps]
        except pywintypes.error:
            return None
    res = subprocess.run(["systemctl", "list-dependencies", "--reverse", "--plain", "--no-pager", name],
                         capture_output=True, text=True, timeout=8)
    if res.returncode != 0:
        return None
    deps = [ln.strip() for ln in res.stdout.splitlines()[1:] if ln.strip().endswith(".service")]
    return [d for d in deps if (lookup(d) or {}).get("status") == "running"]


# --------------------------------------------------------------------------- control

_WIN_ERRORS = {
    5: "Access denied. Controlling this service needs administrator rights; run Agentica as Administrator.",
    1051: "Other running services depend on this service; stop them first.",
    1052: "The requested control is not valid for this service.",
    1053: "The service did not respond to the request in time.",
    1058: "The service is disabled and cannot be started.",
    1060: "The service does not exist.",
    1061: "The service cannot accept control messages at this time.",
    1068: "A service it depends on failed to start.",
}


def _state(name: str) -> str:
    if IS_WINDOWS:
        return WIN_STATE.get(win32serviceutil.QueryServiceStatus(name)[1], "unknown")
    return (lookup(name) or {}).get("status", "unknown")


def _wait_for(name: str, want: str, timeout: float = WAIT_S) -> tuple[str, bool]:
    deadline = time.monotonic() + timeout
    while True:
        st = _state(name)
        if st == want:
            return st, True
        if time.monotonic() > deadline:
            return st, False
        time.sleep(POLL_S)


def _win_send(name: str, verb: str) -> None:
    """Least-privilege handles: connect to the SCM, open the service only for start or stop.
    (win32serviceutil.StartService asks for SC_MANAGER_ALL_ACCESS, which needs admin even
    when the service's own ACL lets this user start it.)"""
    access = win32service.SERVICE_START if verb == "start" else win32service.SERVICE_STOP
    scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
    try:
        hs = win32service.OpenService(scm, name, access | win32service.SERVICE_QUERY_STATUS)
        try:
            if verb == "start":
                win32service.StartService(hs, None)
            else:
                win32service.ControlService(hs, win32service.SERVICE_CONTROL_STOP)
        finally:
            win32service.CloseServiceHandle(hs)
    finally:
        win32service.CloseServiceHandle(scm)


def _send(name: str, verb: str) -> None:
    if IS_WINDOWS:
        try:
            _win_send(name, verb)
        except pywintypes.error as e:
            if (verb, e.winerror) in (("start", 1056), ("stop", 1062)):  # already in that state
                return
            raise ServiceError(_WIN_ERRORS.get(e.winerror, f"{e.strerror} (error {e.winerror})")) from e
        return
    res = subprocess.run(["systemctl", verb, name], capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        msg = (res.stderr or res.stdout).strip() or f"systemctl {verb} failed"
        if "authentication" in msg.lower() or "access denied" in msg.lower():
            msg = "Permission denied. Controlling services needs root (run Agentica with sudo or grant polkit rights)."
        raise ServiceError(msg)


def control(name: str, action: str) -> dict:
    """start | stop | restart, then verify the resulting state."""
    info = lookup(name)
    if info is None:
        raise ServiceError(f"No service named '{name}'.")
    canonical = info["name"]
    before = info["status"]
    t0 = time.perf_counter()
    want = "stopped" if action == "stop" else "running"

    if (action == "start" and before == "running") or (action == "stop" and before == "stopped"):
        return {"service": canonical, "display_name": info["display_name"], "action": action,
                "changed": False, "before": before, "after": before, "verified": True,
                "note": f"already {before}; nothing to do", "elapsed_ms": 0}

    phases = []
    if action in ("stop", "restart") and before != "stopped":
        _send(canonical, "stop")
        st, ok = _wait_for(canonical, "stopped")
        phases.append({"step": "stop", "state": st, "ok": ok})
        if not ok:
            return {"service": canonical, "display_name": info["display_name"], "action": action, "changed": True,
                    "before": before, "after": st, "verified": False, "phases": phases,
                    "note": f"service did not stop within {WAIT_S}s",
                    "elapsed_ms": round((time.perf_counter() - t0) * 1000)}
    if action in ("start", "restart"):
        _send(canonical, "start")
        st, ok = _wait_for(canonical, "running")
        phases.append({"step": "start", "state": st, "ok": ok})

    after = lookup(canonical) or {}
    verified = after.get("status") == want
    out = {"service": canonical, "display_name": info["display_name"], "action": action, "changed": True,
           "before": before, "after": after.get("status"), "verified": verified, "pid": after.get("pid"),
           "elapsed_ms": round((time.perf_counter() - t0) * 1000)}
    if len(phases) > 1:
        out["phases"] = phases
    if not verified:
        out["note"] = f"expected '{want}' but the service is '{after.get('status')}'"
    return out
