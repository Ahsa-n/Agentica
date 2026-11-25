"""
Fleet monitor — polls every registered remote machine every FLEET_INTERVAL seconds.

One round trip per machine per tick: the fixed "metrics" PowerShell script (CPU, memory,
system disk, uptime). Machines are polled in parallel; machines without credentials or
known to be unreachable are skipped without waiting. The latest sample plus a short
history is pushed to the browser on the existing telemetry stream (SSE).
"""
from __future__ import annotations

import asyncio
import time

FLEET_INTERVAL = 7.0        # seconds between polls of each machine
FLEET_TIMEOUT = 20.0        # one poll may not take longer than this
HISTORY = 40                # samples kept per machine (~4.5 minutes)


class FleetMonitor:
    def __init__(self, store, registry, interval: float = FLEET_INTERVAL) -> None:
        self.store = store
        self.registry = registry
        self.interval = interval
        self.status: dict[str, dict] = {}
        self._task: asyncio.Task | None = None

    async def poll(self, m: dict) -> dict:
        st = self.status.setdefault(m["id"], {"cpu_hist": [], "mem_hist": [], "state": "waiting"})
        st.update(label=m["label"], host=m["host"])
        prev = st.get("state")
        host, err = self.registry.for_machine(m)
        if host is None:   # "setup" = no credentials / unsupported; "unreachable" = machine is down
            kind = getattr(err, "kind", "request")
            st.update(state="setup" if kind == "request" else "unreachable", error=str(err), checked=time.time())
            return st
        t0 = time.perf_counter()
        try:
            data = await asyncio.wait_for(asyncio.to_thread(host.metrics), FLEET_TIMEOUT)
        except Exception as e:  # noqa: BLE001 - RemoteError, timeout, ...
            msg = str(e) or f"{m['label']} did not answer within {FLEET_TIMEOUT:.0f}s."
            st.update(state="error", error=msg, checked=time.time())
            if prev != "error":
                await asyncio.to_thread(self.store.record_test, m["id"], False, None, msg)
            return st
        now = time.time()
        st.update(state="ok", error=None, checked=now, updated=now, metrics=data,
                  ms=round((time.perf_counter() - t0) * 1000))
        st["cpu_hist"] = (st["cpu_hist"] + [data.get("cpu_percent", 0)])[-HISTORY:]
        st["mem_hist"] = (st["mem_hist"] + [data.get("memory", {}).get("percent", 0)])[-HISTORY:]
        if prev != "ok":
            await asyncio.to_thread(self.store.record_test, m["id"], True,
                                    {"computer": data.get("computer"), "os": data.get("os")}, None)
        return st

    async def _loop(self) -> None:
        while True:
            started = time.monotonic()
            machines = await asyncio.to_thread(self.store.machines)
            ids = {m["id"] for m in machines}
            for gone in set(self.status) - ids:
                self.status.pop(gone, None)
            if machines:
                await asyncio.gather(*(self.poll(m) for m in machines), return_exceptions=True)
            await asyncio.sleep(max(1.0, self.interval - (time.monotonic() - started)))

    def view(self) -> dict:
        return {"interval": self.interval, "machines": self.status}

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
