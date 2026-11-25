"""
Stage-1 router evaluation (no chat model involved, ~10 s).

    python tests/router_eval.py            # report on the dev and held-out test splits
    python tests/router_eval.py --tune     # grid-search the thresholds on DEV only, then report

Every request below is labelled with the toolset(s) that must be loaded to answer it ([] = no tools:
a general question). None of these sentences appear in router.EXAMPLES. Thresholds are tuned on DEV;
TEST is never used for tuning, so its numbers are the honest ones.

Metrics
  exact     selected toolsets == gold
  covered   every gold toolset was selected (the LLM can answer without an extra load_tools round)
  no-tools  general questions that correctly loaded nothing
  extra     average number of toolsets loaded that were not needed
"""
import asyncio
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import router as R                       # noqa: E402
from tools import TOOLSETS               # noqa: E402

M, S, N, A, X = ["monitor"], ["storage"], ["services"], ["apps"], ["network"]

# (request, gold toolsets, previous request or None, machine names in play)
DEV = [
    ("whats the cpu at", M, None), ("my pc is crawling, what's going on", M, None),
    ("how much memory does the server have left", M, None), ("list processes by memory", M, None),
    ("what's the uptime on web-01", M, None), ("is web-01 under heavy load", M, None),
    ("which program is maxing out the processor", M, None),
    ("is my hard drive running out of space", S, None), ("how full is the D: drive", S, None),
    ("free space on the linux box", S, None), ("check storage on web-01", S, None),
    ("is /srv/data almost full", S, None),
    ("is the spooler running", N, None), ("restart the bits service", N, None),
    ("start nginx on web-01", N, None), ("stop the sql server agent service", N, None),
    ("are any services that should auto start stopped", N, None), ("is cron running on the server", N, None),
    ("why won't the wuauserv service start", N, None),
    ("what's this machine's ip", X, None), ("is the network adapter up", X, None),
    ("how much data is the nic pushing right now", X, None), ("list my network cards", X, None),
    ("open notepad++", A, None), ("launch the terminal app", A, None), ("fire up firefox", A, None),
    ("is the Ollama API up", A, None), ("check if agentica-web is responding", A, None),
    ("start watching discord", A, None), ("is my monitored app healthy", A, None),
    ("what does a dns server do", [], None), ("explain the difference between http and https", [], None),
    ("how do I add a user in linux", [], None), ("write a powershell command to list files by size", [], None),
    ("what is a reverse proxy", [], None), ("good morning", [], None), ("what is kubernetes", [], None),
    ("how does ssh key authentication work", [], None),
    ("check disk space and memory", S + M, None), ("is the spooler running and how much free space is there", N + S, None),
    ("show cpu usage, then the ip addresses", M + X, None),
    ("and on web-01?", S, "how much disk space is left"), ("restart it", N, "is the spooler service running"),
    ("what about memory", M, "what's the cpu usage"),
]
TEST = [
    ("what's using my ram", M, None), ("give me a health check of web-01", M, None),
    ("top 5 processes by cpu", M, None), ("the computer is freezing all the time", M, None),
    ("how long since the last reboot", M, None), ("is the server overloaded", M, None),
    ("how much space is on my C drive", S, None), ("am I low on disk", S, None),
    ("check the volumes on web-01", S, None), ("is the boot partition full", S, None),
    ("is the windows update service running", N, None), ("restart postgresql", N, None),
    ("stop the print spooler", N, None), ("check the status of the docker daemon", N, None),
    ("list failed services on web-01", N, None), ("start the mysql service", N, None),
    ("what's my local ip address", X, None), ("is the wifi adapter connected", X, None),
    ("how much bandwidth am I using", X, None), ("what's the link speed of eth0", X, None),
    ("open visual studio code", A, None), ("launch slack", A, None), ("open the snipping tool", A, None),
    ("is our website up", A, None), ("is Visual Studio Code not responding", A, None),
    ("monitor postgres as an app", A, None),
    ("what is a firewall", [], None), ("how do I reset a windows password", [], None),
    ("explain load balancing", [], None), ("what's the difference between ram and storage", [], None),
    ("how to schedule a task in windows", [], None), ("thank you!", [], None), ("who made you", [], None),
    ("check cpu and network throughput", M + X, None), ("restart nginx and check disk usage", N + S, None),
    ("open edge and tell me the memory usage", A + M, None),
    ("and the network?", X, "check the cpu"), ("now stop it", N, "start the bits service"),
    ("what about web-01", M, "how is this machine doing"),
]
NAMES = ["web-01", "DESKTOP-R8883BN", "10.0.0.21"]
APPS = ["agentica-web", "Ollama API", "Visual Studio Code"]


def dynamic():
    return {"apps": [p.format(a) for a in APPS for p in ("is {} running", "check {}")]}


async def main(tune: bool) -> int:
    rt = R.Router(TOOLSETS, "http://127.0.0.1:11434", ROOT / "data" / "router_index.json", dynamic)
    await rt.ensure_index()
    memo: dict[str, object] = {}
    real = rt.embed

    async def embed(texts):                       # memoise: tuning re-routes every request many times
        missing = [t for t in texts if t not in memo]
        if missing:
            for t, v in zip(missing, await real(missing)):
                memo[t] = v
        import numpy as np
        return np.asarray([memo[t] for t in texts])
    rt.embed = embed

    async def run(rows):
        out = []
        for row in rows:
            text, gold, prev = row
            d = await rt.route(text, previous=prev, names=NAMES)
            out.append((text, set(gold), set(d.domains), d))
        return out

    def metrics(res):
        n = len(res)
        exact = sum(g == s for _, g, s, _ in res)
        cov = sum(g <= s for _, g, s, _ in res)
        gen = [(g, s) for _, g, s, _ in res if not g]
        none_ok = sum(not s for g, s in gen)
        extra = sum(len(s - g) for _, g, s, _ in res) / n
        return {"exact": exact / n, "covered": cov / n, "no-tools": none_ok / max(1, len(gen)), "extra": extra, "n": n}

    if tune:
        best = None
        for ms, nm, sm in itertools.product([0.40, 0.42, 0.44, 0.46, 0.48, 0.50, 0.52, 0.54, 0.56],
                                            [-0.04, -0.02, 0.0, 0.02, 0.04, 0.06],
                                            [0.0, 0.02, 0.04, 0.06, 0.08]):
            R.MIN_SCORE, R.NONE_MARGIN, R.SECOND_MARGIN = ms, nm, sm
            m = metrics(await run(DEV))
            key = (round(m["exact"] + m["covered"], 4), -m["extra"])
            if best is None or key > best[0]:
                best = (key, (ms, nm, sm), m)
        (ms, nm, sm), m = best[1], best[2]
        R.MIN_SCORE, R.NONE_MARGIN, R.SECOND_MARGIN = ms, nm, sm
        print(f"best on DEV: MIN_SCORE={ms} NONE_MARGIN={nm} SECOND_MARGIN={sm}  "
              f"exact {m['exact']:.0%} covered {m['covered']:.0%}")

    ok = True
    for name, rows in (("DEV", DEV), ("TEST (held out)", TEST)):
        res = await run(rows)
        m = metrics(res)
        print(f"\n{name}: {m['n']} requests  exact {m['exact']:.0%}  covered {m['covered']:.0%}  "
              f"no-tools {m['no-tools']:.0%}  extra {m['extra']:.2f}/request")
        for text, g, s, d in res:
            if g != s:
                top = sorted(d.scores.items(), key=lambda kv: -kv[1])[:3]
                print(f"   {'MISS ' if not g <= s else 'extra'} {text!r:52} gold={sorted(g) or '-'} got={sorted(s) or '-'}  "
                      + " ".join(f"{c}:{v:.2f}" for c, v in top))
        if name.startswith("TEST"):
            ok = m["covered"] >= 0.85 and m["no-tools"] >= 0.8
    print(f"\nrules: MIN_SCORE={R.MIN_SCORE} NONE_MARGIN={R.NONE_MARGIN} SECOND_MARGIN={R.SECOND_MARGIN} TOP_K={R.TOP_K}")
    await rt.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main("--tune" in sys.argv)))
