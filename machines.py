"""
Machine registry helpers: parse operator input and probe reachability.

Reachability = a TCP connect to the management port (WinRM 5986/5985 or SSH 22).
It proves the port is open, not that credentials work; authentication arrives
with the WinRM / SSH modules.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import time

import os

TRANSPORTS = {"winrm-https": 5986, "winrm-http": 5985, "ssh": 22}
if os.environ.get("AGENTICA_DEV") == "1":
    TRANSPORTS["local-ps"] = 0        # dev-only loopback (see hosts.LocalPSHost)
OS_DEFAULT_TRANSPORT = {"windows": "winrm-http", "linux": "ssh"}
MAX_MACHINES = 200

_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
HOST_RE = re.compile(rf"^(?=.{{1,253}}$){_LABEL}(?:\.{_LABEL})*$")


def _valid_host(h: str) -> bool:
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return bool(HOST_RE.match(h)) and not h.replace(".", "").isdigit()


def parse_hosts(text: str) -> tuple[list[tuple[str, int | None]], list[str]]:
    """'10.0.0.5, web-01:5985\\nsrv.lab.local' -> ([(host, port|None), ...], [invalid tokens])."""
    valid, invalid, seen = [], [], set()
    for tok in re.split(r"[\n\r,;]+", text):
        tok = tok.strip()
        if not tok:
            continue
        if re.search(r"\s", tok):          # 'bad host' is one wrong entry, not two machines
            invalid.append(tok)
            continue
        host, port = tok, None
        m = re.match(r"^\[([0-9A-Fa-f:.]+)\](?::(\d+))?$", tok)          # [ipv6]:port
        if m:
            host, port = m.group(1), int(m.group(2)) if m.group(2) else None
        elif tok.count(":") == 1:                                          # host:port
            host, p = tok.split(":")
            port = int(p) if p.isdigit() else -1
        if (port is not None and not 1 <= port <= 65535) or not _valid_host(host):
            invalid.append(tok)
            continue
        key = host.lower()
        if key not in seen:
            seen.add(key)
            valid.append((host, port))
    return valid, invalid


class Prober:
    def __init__(self, store, interval: float = 15.0) -> None:
        self.store = store
        self.interval = interval
        self.status: dict[str, dict] = {}
        self._task: asyncio.Task | None = None

    async def probe(self, m: dict) -> dict:
        if m["transport"] == "local-ps":
            st = {"state": "reachable", "latency_ms": 0, "checked": time.time()}
            self.status[m["id"]] = st
            return st
        t0 = time.perf_counter()
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(m["host"], m["port"]), timeout=2.5)
            writer.close()
            st = {"state": "reachable", "latency_ms": round((time.perf_counter() - t0) * 1000)}
        except asyncio.TimeoutError:
            st = {"state": "unreachable", "error": "timed out"}
        except OSError as e:
            st = {"state": "unreachable", "error": e.strerror or str(e)}
        st["checked"] = time.time()
        self.status[m["id"]] = st
        return st

    async def _loop(self) -> None:
        while True:
            machines = await asyncio.to_thread(self.store.machines)
            if machines:
                await asyncio.gather(*(self.probe(m) for m in machines), return_exceptions=True)
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
