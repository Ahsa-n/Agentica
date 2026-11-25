"""
Stage 1 of Agentica's two-stage tool router.

    request ──embed──▶ compare with example requests of every toolset ──▶ 0–3 toolsets loaded
                                                                          ──▶ stage 2: the LLM picks the
                                                                              exact tool + arguments
                                                                              from only those tools

No LLM is involved in stage 1. Each toolset is described by short example requests (EXAMPLES below,
plus "is <app> running" phrases for every monitored app). They are embedded once and cached on disk;
a request is embedded (~50 ms on CPU) and scored against them. A "none" class (general IT questions,
how-tos, chit-chat) lets the router load nothing at all, so general questions stay tool-free.

The embedding model is EmbeddingGemma (308M parameters) served by the local Ollama, pinned to the CPU
so it takes no GPU memory from the chat model. If it is unavailable, routing falls back to the LLM's
own `load_tools` call (the previous behaviour), so the router can only help, never block.

Request text is normalised first: machine names and addresses are removed (with the "on"/"for"
in front of them), so "disk space on web-01" and "disk space" route the same way. Multi-part
requests ("restart nginx and check disk usage") are also scored clause by clause, and a short
follow-up ("and on web-01?", "restart it") that is not confidently routed on its own is scored
together with the previous request.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx
import numpy as np

log = logging.getLogger("agentica.router")

MODEL = os.environ.get("AGENTICA_EMBED_MODEL", "embeddinggemma")
PREFIX = "task: sentence similarity | query: "      # EmbeddingGemma's prompt for symmetric similarity
KEEP_ALIVE = "60m"
NONE = "none"

# Decision rules (tuned on tests/router_eval.py's dev split, reported on its held-out test split).
TOP_K = 2           # a class's score = mean of its TOP_K most similar examples
MIN_SCORE = 0.50    # a toolset needs at least this score to be loaded (dev results identical for 0.40-0.56: the "none" class does the real work)
NONE_MARGIN = 0.0   # ... and must beat the "no tools" class by this much
SECOND_MARGIN = 0.02  # a 2nd toolset from the same sentence is loaded if within this of the best
MAX_SETS = 3        # never load more than this many toolsets in one turn
SHORT_WORDS = 6     # a short follow-up with no clear route is also scored together with the previous request
CONFIDENT = 0.62    # ... "clear" = its own best toolset scores at least this

EXAMPLES: dict[str, list[str]] = {
    "monitor": [
        "how is this machine doing",
        "check the health of the server",
        "what is the cpu usage right now",
        "why is my computer so slow",
        "is the processor overloaded",
        "how much memory is being used",
        "how much ram is free",
        "which processes are using the most cpu",
        "what is eating all my memory",
        "show me the top processes",
        "how long has the machine been up",
        "when was the server last rebooted",
        "is swap being used",
        "give me a quick system overview",
        "the laptop fan is loud and everything is lagging",
        "how many cores does it have",
        "check load and memory pressure on the box",
        "is anything hogging resources",
    ],
    "storage": [
        "how much disk space is left",
        "is my drive full",
        "check free space on all volumes",
        "which disk is almost full",
        "how big is the C drive and how much is used",
        "am I running out of storage",
        "show disk usage",
        "is the root partition full",
        "how much space is free on /var",
        "list the drives and their capacity",
        "the server says no space left on device",
        "check the volumes for capacity problems",
        "do I have enough room to install a 20 GB update",
        "what percentage of the data disk is used",
    ],
    "services": [
        "is the print spooler service running",
        "restart the spooler service",
        "start the nginx service",
        "stop the windows update service",
        "check the status of sshd",
        "is postgresql running",
        "list services that should be running but are stopped",
        "which automatic services are not running",
        "show failed systemd units",
        "restart apache on the web server",
        "the dhcp client service is stopped, start it",
        "is the mysql daemon up",
        "bring the docker service back up",
        "what services are running",
        "find the service called windows search",
        "is the windows time service ok",
        "restart wuauserv",
        "is the redis-server unit active",
    ],
    "network": [
        "what is my ip address",
        "show the network interfaces",
        "is the ethernet adapter connected",
        "how fast is the network link",
        "how much bandwidth is being used right now",
        "what is the current download and upload throughput",
        "which network adapters are up",
        "is wifi connected",
        "show the ipv4 addresses of the server",
        "the network feels slow, check the interfaces",
        "what is the mac address of the network card",
        "is the link speed 1 gigabit",
        "how much traffic is going through eth0",
    ],
    "apps": [
        "open vs code",
        "launch chrome",
        "start notepad",
        "open the calculator app",
        "can you open microsoft edge for me",
        "run spotify",
        "is our web app up",
        "check the status of the monitored applications",
        "is the api responding",
        "are my apps healthy",
        "is sql server application running and responding",
        "start monitoring visual studio code",
        "watch the ollama app for me",
        "add my app to monitoring",
        "is the website down",
        "is the application frozen or not responding",
        "has the app restarted recently",
        "register teams as a monitored application",
    ],
    NONE: [
        "what is dns",
        "explain what a subnet mask is",
        "how does raid 5 work",
        "what is the difference between tcp and udp",
        "how do I write a powershell script to rename files",
        "what does the chmod command do",
        "explain how dhcp works",
        "what is a systemd unit file",
        "give me a bash one-liner to find large files",
        "what is active directory",
        "how do I set up a cron job",
        "write a regex for an email address",
        "what are best practices for password policies",
        "hi",
        "hello, who are you",
        "thanks",
        "what can you do",
        "tell me a joke",
        "summarise what we discussed",
        "what is the capital of france",
        "explain the osi model",
        "how do vlans work",
        "what is the difference between a process and a thread",
        "how should I plan backups for a small office",
    ],
}

_CLAUSE = re.compile(r"\s*(?:[,;]|\band then\b|\bthen\b|\band also\b|\balso\b|\bas well as\b|\bplus\b|\band\b)\s*",
                     re.I)


@dataclass
class Decision:
    domains: list[str]                       # toolsets to load, best first
    scores: dict[str, float]                 # whole-request score per class
    ms: int = 0
    via: str = "router"
    error: str | None = None
    parts: list[dict] = field(default_factory=list)   # per clause (multi-part requests)
    context_used: bool = False


class Router:
    def __init__(self, toolsets: dict, ollama_url: str, cache_path: Path,
                 dynamic: Callable[[], dict[str, list[str]]] | None = None, model: str = MODEL) -> None:
        self.classes = [i for i, s in toolsets.items() if not s.get("card_only")] + [NONE]
        self.ollama = ollama_url.rstrip("/")
        self.cache_path = cache_path
        self.dynamic = dynamic or (lambda: {})
        self.model = model
        self.http: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._cache: dict[str, list[float]] = {}
        self._index_key = None
        self._labels: list[str] = []
        self._texts: list[str] = []
        self._matrix: np.ndarray | None = None
        self.ready = False
        self.error: str | None = None
        self.stats = {"routed": 0, "avg_ms": 0.0}
        self._load_cache()

    # ---------------------------------------------------------------- embedding
    def _client(self) -> httpx.AsyncClient:
        if self.http is None:
            self.http = httpx.AsyncClient(base_url=self.ollama, timeout=httpx.Timeout(60.0, connect=3.0))
        return self.http

    async def embed(self, texts: list[str]) -> np.ndarray:
        r = await self._client().post("/api/embed", json={
            "model": self.model, "input": [PREFIX + t for t in texts], "keep_alive": KEEP_ALIVE,
            "options": {"num_gpu": 0}})                       # CPU: leave the GPU to the chat model
        if r.status_code != 200:
            try:
                msg = r.json().get("error", r.text)
            except ValueError:
                msg = r.text
            if "not found" in msg:
                msg = f"embedding model '{self.model}' is not installed (ollama pull {self.model})"
            raise RuntimeError(msg)
        m = np.asarray(r.json()["embeddings"], dtype=np.float32)
        return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)

    def _key(self, text: str) -> str:
        return hashlib.sha1(f"{self.model}\0{PREFIX}{text}".encode()).hexdigest()

    def _load_cache(self) -> None:
        try:
            d = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if d.get("model") == self.model:
                self._cache = d.get("vectors", {})
        except (OSError, ValueError):
            self._cache = {}

    def _save_cache(self, keep: set[str]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"model": self.model, "vectors": {k: v for k, v in self._cache.items() if k in keep}}
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(self.cache_path)
        except OSError:
            log.exception("router cache write failed")

    # ---------------------------------------------------------------- index
    def examples(self) -> list[tuple[str, str]]:
        pairs = [(c, t) for c in self.classes for t in EXAMPLES.get(c, [])]
        for c, texts in (self.dynamic() or {}).items():
            if c in self.classes:
                pairs += [(c, t) for t in texts]
        return list(dict.fromkeys(pairs))

    async def ensure_index(self) -> None:
        """(Re)build the example matrix if the example set changed. Only new texts are embedded."""
        pairs = self.examples()
        key = hash(tuple(pairs))
        if key == self._index_key and self._matrix is not None:
            return
        async with self._lock:
            if key == self._index_key and self._matrix is not None:
                return
            todo = [t for _, t in pairs if self._key(t) not in self._cache]
            for i in range(0, len(todo), 64):
                batch = todo[i:i + 64]
                vecs = await self.embed(batch)
                for t, v in zip(batch, vecs):
                    self._cache[self._key(t)] = [round(float(x), 6) for x in v]
            keys = [self._key(t) for _, t in pairs]
            if todo:
                self._save_cache(set(keys))
            self._labels = [c for c, _ in pairs]
            self._texts = [t for _, t in pairs]
            self._matrix = np.asarray([self._cache[k] for k in keys], dtype=np.float32)
            self._index_key = key
            self.ready, self.error = True, None

    async def warm(self) -> None:
        """Build the index and load the model into memory (called at server start)."""
        try:
            t0 = time.monotonic()
            await self.ensure_index()
            await self.embed(["warm up"])
            log.info("router ready: %d examples, %.1fs", len(self._labels), time.monotonic() - t0)
        except Exception as e:  # noqa: BLE001
            self.ready, self.error = False, str(e) or type(e).__name__
            log.warning("router unavailable (%s); the model will load tools itself", self.error)

    # ---------------------------------------------------------------- scoring
    def _class_scores(self, vec: np.ndarray) -> dict[str, float]:
        sims = self._matrix @ vec
        out = {}
        for c in self.classes:
            s = np.sort(sims[[i for i, lab in enumerate(self._labels) if lab == c]])[::-1]
            out[c] = float(s[:TOP_K].mean()) if len(s) else 0.0
        return out

    @staticmethod
    def _passes(sc: dict[str, float], c: str) -> bool:
        return sc[c] >= MIN_SCORE and sc[c] >= sc[NONE] + NONE_MARGIN

    def _pick(self, sc: dict[str, float], second: bool) -> list[str]:
        tools = sorted((c for c in sc if c != NONE), key=lambda c: -sc[c])
        if not tools or not self._passes(sc, tools[0]):
            return []
        pick = [tools[0]]
        if second:
            pick += [c for c in tools[1:] if self._passes(sc, c) and sc[c] >= sc[tools[0]] - SECOND_MARGIN]
        return pick

    @staticmethod
    def normalise(text: str, names: list[str]) -> str:
        t = " ".join(text.split())
        pre = r"(?:\b(?:on|for|at|of|from|in|to)\s+)?"
        for n in sorted({n for n in names if n}, key=len, reverse=True):
            t = re.sub(rf"{pre}(?<![\w.-]){re.escape(n)}(?![\w-])", " ", t, flags=re.I)
        t = re.sub(rf"{pre}\b\d{{1,3}}(?:\.\d{{1,3}}){{3}}\b", " ", t)
        t = re.sub(r"\s+([?.!,])", r"\1", " ".join(t.split()))
        return t or text

    @staticmethod
    def clauses(text: str) -> list[str]:
        parts = [p.strip(" .?!") for p in _CLAUSE.split(text)]
        parts = [p for p in parts if len(re.sub(r"[^a-z]", "", p.lower())) >= 3]
        return parts if len(parts) > 1 else []

    async def route(self, text: str, *, previous: str | None = None, names: list[str] | None = None) -> Decision:
        t0 = time.monotonic()
        try:
            await self.ensure_index()
            q = self.normalise(text, names or [])
            parts = self.clauses(q)[:4]
            inputs = [q] + parts
            ctx_text = None
            if previous and len(q.split()) <= SHORT_WORDS:
                ctx_text = self.normalise(previous, names or []) + ". " + q
                inputs.append(ctx_text)
            vecs = await self.embed(inputs)
        except Exception as e:  # noqa: BLE001
            self.ready, self.error = False, str(e) or type(e).__name__
            return Decision([], {}, round((time.monotonic() - t0) * 1000), error=self.error)
        self.ready, self.error = True, None

        whole = self._class_scores(vecs[0])
        domains = self._pick(whole, second=True)
        part_info = []
        general = whole[NONE] >= max(v for c, v in whole.items() if c != NONE)
        for p, v in zip([] if general else parts, vecs[1:1 + len(parts)]):    # clauses of a general question don't count
            sc = self._class_scores(v)
            got = self._pick(sc, second=False)
            part_info.append({"text": p, "domains": got, "best": round(max(sc.values()), 3)})
            domains += [d for d in got if d not in domains]
        used_ctx = False
        if ctx_text is not None and (not domains or whole[domains[0]] < CONFIDENT):
            csc = self._class_scores(vecs[-1])
            got = self._pick(csc, second=False)
            if got:
                domains, used_ctx = got, True
                whole = {c: max(whole[c], csc[c]) for c in whole}
        domains = sorted(dict.fromkeys(domains), key=lambda c: -whole[c])[:MAX_SETS]
        ms = round((time.monotonic() - t0) * 1000)
        n = self.stats["routed"] = self.stats["routed"] + 1
        self.stats["avg_ms"] += (ms - self.stats["avg_ms"]) / n
        return Decision(domains, {c: round(s, 3) for c, s in whole.items()}, ms, parts=part_info,
                        context_used=used_ctx)

    def status(self) -> dict:
        return {"model": self.model, "ready": self.ready, "error": self.error, "examples": len(self._labels),
                "classes": self.classes, "rules": {"top_k": TOP_K, "min_score": MIN_SCORE,
                                                   "none_margin": NONE_MARGIN, "second_margin": SECOND_MARGIN,
                                                   "max_sets": MAX_SETS},
                "routed": self.stats["routed"], "avg_ms": round(self.stats["avg_ms"])}

    async def close(self) -> None:
        if self.http:
            await self.http.aclose()
