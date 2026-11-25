"""
Finding, describing and launching applications on THIS PC (Windows).

  windows_by_pid()     visible top-level windows per process, and whether each is hung
                       (IsHungAppWindow: the same "Not responding" Task Manager shows)
  file_description()   friendly name of an executable ("Code.exe" -> "Visual Studio Code")
  listening_ports()    TCP ports each process listens on (suggested port checks)
  running_apps()       running programs grouped by process name, with the above
  installed_apps()     everything in the Start menu (desktop + Store apps), with its .exe when known
  find_installed()     fuzzy match a name the operator typed against installed_apps()
  launch()             open an installed app through Explorer (runs as the signed-in user, never
                       elevated) and verify that a window / process actually appeared
"""
from __future__ import annotations

import difflib
import json
import os
import platform
import re
import subprocess
import threading
import time

import psutil

IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    import ctypes
    import ctypes.wintypes as W

    import win32api

_INSTALLED_TTL = 600          # seconds the installed-app list is cached
_installed: tuple[float, list[dict]] = (0.0, [])
_installed_lock = threading.Lock()
_desc_cache: dict[str, str | None] = {}


# --------------------------------------------------------------------------- windows

def windows_by_pid() -> dict[int, list[dict]]:
    """{pid: [{"hwnd", "title", "hung"}]} for visible, titled, top-level windows."""
    if not IS_WINDOWS:
        return {}
    u = ctypes.windll.user32
    out: dict[int, list[dict]] = {}

    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd) and not u.GetWindow(hwnd, 4):        # 4 = GW_OWNER
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                pid = W.DWORD()
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                out.setdefault(pid.value, []).append(
                    {"hwnd": int(hwnd), "title": buf.value[:80], "hung": bool(u.IsHungAppWindow(hwnd))})
        return True

    u.EnumWindows(cb, 0)
    return out


def file_description(exe: str | None) -> str | None:
    if not exe or not IS_WINDOWS:
        return None
    if exe not in _desc_cache:
        try:
            lang, cp = win32api.GetFileVersionInfo(exe, "\\VarFileInfo\\Translation")[0]
            d = win32api.GetFileVersionInfo(exe, f"\\StringFileInfo\\{lang:04x}{cp:04x}\\FileDescription")
            _desc_cache[exe] = (d or "").strip() or None
        except Exception:  # noqa: BLE001 - many executables have no version resource
            _desc_cache[exe] = None
    return _desc_cache[exe]


def listening_ports() -> dict[int, list[int]]:
    out: dict[int, set[int]] = {}
    try:
        for c in psutil.net_connections("inet"):
            if c.status == psutil.CONN_LISTEN and c.pid:
                out.setdefault(c.pid, set()).add(c.laddr.port)
    except (psutil.AccessDenied, OSError):
        pass
    return {pid: sorted(p) for pid, p in out.items()}


def _stem(name: str) -> str:
    return re.sub(r"\.exe$", "", name or "", flags=re.I)


# --------------------------------------------------------------------------- running apps (picker / register)

_SYSTEM = {"system", "registry", "idle", "smss", "csrss", "wininit", "winlogon", "services", "lsass", "svchost",
           "fontdrvhost", "dwm", "memory compression", "secure system", "sihost", "taskhostw", "ctfmon",
           "runtimebroker", "conhost", "dllhost", "searchhost", "startmenuexperiencehost", "textinputhost",
           "shellexperiencehost", "applicationframehost", "systemsettingsbroker", "audiodg", "spoolsv",
           "wmiprvse", "searchindexer", "msmpeng", "nissrv", "securityhealthservice", "wudfhost", "lsaiso"}


def running_apps(include_background: bool = False, sampler=None) -> list[dict]:
    """Running programs grouped by process name (largest first). By default: programs with a window or that
    listen on a TCP port (servers); include_background adds everything else."""
    wins = windows_by_pid()
    ports = listening_ports()
    cpu_by_pid = {}
    if sampler is not None:
        with sampler.lock:
            cpu_by_pid = {p["pid"]: p["cpu"] for p in sampler.procs}
    groups: dict[str, dict] = {}
    for p in psutil.process_iter(["pid", "name", "exe", "memory_info"]):
        try:
            name = p.info["name"] or ""
            stem = _stem(name)
            if not stem or stem.lower() in _SYSTEM or p.pid in (0, 4):
                continue
            g = groups.setdefault(stem.lower(), {"process": stem, "display": None, "exe": p.info.get("exe"), "count": 0,
                                                 "memory_mb": 0.0, "cpu_percent": 0.0, "has_window": False,
                                                 "windows": [], "ports": set()})
            g["count"] += 1
            mi = p.info.get("memory_info")
            g["memory_mb"] += (mi.rss if mi else 0) / 1024**2
            g["cpu_percent"] += cpu_by_pid.get(p.pid, 0.0)
            if p.pid in wins:
                g["has_window"] = True
                g["windows"] += [w["title"] for w in wins[p.pid]]
            g["ports"].update(ports.get(p.pid, []))
            if not g["exe"] and p.info.get("exe"):
                g["exe"] = p.info["exe"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    out = []
    for g in groups.values():
        if not include_background and not g["has_window"] and not g["ports"]:
            continue
        g["display"] = file_description(g["exe"]) or g["process"]
        out.append({"process": g["process"], "display": g["display"], "count": g["count"],
                    "memory_mb": round(g["memory_mb"], 1), "cpu_percent": round(g["cpu_percent"], 1),
                    "has_window": g["has_window"], "windows": g["windows"][:3], "ports": sorted(g["ports"])[:8]})
    out.sort(key=lambda a: (not a["has_window"], -a["memory_mb"]))
    return out


# --------------------------------------------------------------------------- installed apps (open from chat)

_LIST_APPS = r"""
$sh = New-Object -ComObject Shell.Application
@($sh.NameSpace('shell:::{4234d49b-0245-4df3-b780-3893943456e1}').Items() | ForEach-Object {
  [ordered]@{ name = $_.Name; app_id = $_.Path; target = $_.ExtendedProperty('System.Link.TargetParsingPath') } }) |
  ConvertTo-Json -Compress
"""


def installed_apps(refresh: bool = False) -> list[dict]:
    """Start-menu apps on this PC: [{name, app_id, exe}] (exe = None for Store apps). Cached for 10 minutes."""
    global _installed
    if not IS_WINDOWS:
        return []
    with _installed_lock:
        ts, apps = _installed
        if not refresh and apps and time.time() - ts < _INSTALLED_TTL:
            return apps
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _LIST_APPS],
                           capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        raw = json.loads(r.stdout or "[]")
        raw = raw if isinstance(raw, list) else [raw]
        apps = []
        for a in raw:
            name, target = (a.get("name") or "").strip(), a.get("target") or ""
            if not name or re.search(r"\buninstall", name, re.I):
                continue
            apps.append({"name": name, "app_id": a.get("app_id"),
                         "exe": target if target.lower().endswith(".exe") else None,
                         "document": bool(target) and not target.lower().endswith(".exe")})
        _installed = (time.time(), apps)
        return apps


def _tokens_match(query: str, name: str) -> bool:
    """Every query word matches a name word by prefix, or the initials of consecutive name words
    ("vs code" -> "Visual Studio Code", "ms teams" -> "Microsoft Teams")."""
    words = re.findall(r"[a-z0-9]+", name)
    initials = {"".join(w[0] for w in words[i:j]) for i in range(len(words)) for j in range(i + 2, len(words) + 1)}
    return all(any(w.startswith(t) for w in words) or t in initials for t in re.findall(r"[a-z0-9]+", query))


_VENDOR_WORDS = {"microsoft", "ms", "windows", "win", "app", "the"}


def _score(query: str, app: dict) -> float:
    q = query.lower().strip()
    s = _score1(q, app)
    words = re.findall(r"[a-z0-9]+", q)
    rest = " ".join(w for w in words if w not in _VENDOR_WORDS)      # "ms edge" -> "edge", "win terminal" -> "terminal"
    if rest and rest != q:
        s = max(s, _score1(rest, app) - 3)
    return s


def _score1(q: str, app: dict) -> float:
    n = app["name"].lower()
    words = re.findall(r"[a-z0-9]+", n)
    joined = q.replace(" ", "")
    if len(words) > 1 and joined in ("".join(words), "".join(w[0] for w in words[:-1]) + words[-1]):
        return 86 - (15 if app.get("document") else 0)                 # "vscode", "visualstudiocode"
    exe = _stem(os.path.basename(app["exe"] or "")).lower()
    if q == n:
        s = 100
    elif q == exe:
        s = 92
    elif n.startswith(q):
        s = 88
    elif all(t in n for t in q.split()):
        s = 80
    elif _tokens_match(q, n):
        s = 78
    elif q in n:
        s = 72
    else:
        s = difflib.SequenceMatcher(None, q, n).ratio() * 70
    if app.get("document"):
        s -= 15            # manuals / help pages are rarely what "open X" means
    return s


def find_installed(query: str) -> tuple[dict | None, list[dict]]:
    """Best installed app for `query`, plus the top candidates (for 'did you mean')."""
    apps = installed_apps()
    ranked, seen = [], set()
    for a in sorted(apps, key=lambda a: _score(query, a), reverse=True):
        if a["name"].lower() not in seen:          # the Start menu can list the same name twice
            seen.add(a["name"].lower())
            ranked.append(a)
    best = ranked[0] if ranked and _score(query, ranked[0]) >= 60 else None
    return best, ranked[:5]


def launch(app: dict, timeout: float = 15.0) -> dict:
    """Open an installed app via Explorer (shell:AppsFolder) and verify a window or process appeared."""
    expected = _stem(os.path.basename(app["exe"])).lower() if app.get("exe") else None
    before_pids = set(psutil.pids())
    before_wins = {w["hwnd"] for ws in windows_by_pid().values() for w in ws}
    t0 = time.perf_counter()
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app['app_id']}"],
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    seen_process = None
    seen_at = 0.0
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.4)
        if seen_process and time.monotonic() - seen_at > 3:
            break       # the program is running; its window may belong to another process (e.g. a terminal)
        wins = windows_by_pid()
        for pid, ws in wins.items():
            new = [w for w in ws if w["hwnd"] not in before_wins]
            if not new:
                continue
            try:
                pname = _stem(psutil.Process(pid).name())
            except psutil.Error:
                continue
            if expected is None or pname.lower() == expected:
                return {"opened": app["name"], "process": pname, "pid": pid, "window": new[0]["title"],
                        "verified": True, "elapsed_ms": round((time.perf_counter() - t0) * 1000)}
        if expected and seen_process is None:
            for pid in set(psutil.pids()) - before_pids:
                try:
                    if _stem(psutil.Process(pid).name()).lower() == expected:
                        seen_process = pid
                        seen_at = time.monotonic()
                except psutil.Error:
                    continue
    out = {"opened": app["name"], "verified": False, "elapsed_ms": round((time.perf_counter() - t0) * 1000)}
    if seen_process:
        out.update(process=expected, pid=seen_process, verified=True,
                   note="the program started but has not shown a window yet")
    else:
        out["note"] = (f"no new window appeared within {timeout:.0f}s; the app may already be open in the background, "
                       "or still starting")
    return out
