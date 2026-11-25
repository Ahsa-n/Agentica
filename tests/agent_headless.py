"""
Headless agent tests - the LangGraph agent with no server and no browser (the benchmark path).

    python tests/agent_headless.py

Needs Ollama with qwen3.5:9b. Uses its own databases under tests/.tmp (never data/).
Toggles the harmless wcncsvc service (start / stop) and leaves it stopped.
"""
import asyncio, json, os, shutil, sys, time
from pathlib import Path

os.environ["AGENTICA_DEV"] = "1"                  # enables the loopback 'local-ps' remote transport
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = ROOT / "tests" / ".tmp"
shutil.rmtree(TMP, ignore_errors=True)

from store import Store
from hosts import HostRegistry, LOCAL
from policy import PolicyEngine
from actions import Actions
from agent import Agent
from router import Router
from tools import TOOLS, TOOLSETS
from telemetry import HOSTNAME, os_label, sampler
import services

MODEL = "qwen3.5:9b"
T0 = time.time()
results = []


def build(embed_model=None):
    store = Store(TMP / "agentica.db")
    registry = HostRegistry(store)
    policy = PolicyEngine(ROOT / "policy.yaml", TOOLS, HOSTNAME, registry.resolve)
    actions = Actions(store, policy)
    router = Router(TOOLSETS, "http://127.0.0.1:11434", TMP / "router_index.json",
                    **({"model": embed_model} if embed_model else {}))
    agent = Agent(store=store, actions=actions, tools=TOOLS, toolsets=TOOLSETS, ollama_url="http://127.0.0.1:11434",
                  local_name=HOSTNAME, os_label=os_label, checkpoint_path=TMP / "checkpoints.db", router=router)
    return store, agent


def svc(name):
    return services.lookup(name)["status"]


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""), flush=True)


def summary(r):
    calls = ", ".join(f"{c['tool']}({json.dumps(c['args'])})→{c['decision']}{'/' + c['approval'] if c['approval'] else ''}"
                      f"{'@' + c['machine'] if c['machine'] and c['machine'] != HOSTNAME else ''}" for c in r["tool_calls"])
    s = r["stats"] or {}
    rt = r.get("routed") or {}
    print(f"    routed={rt.get('domains')} ({rt.get('ms')} ms) load_tools={r['load_tools_calls']} loaded={r['loaded']} calls=[{calls}] notices={len(r['notices'])} grounded={r['grounded']} "
          f"decided={r['decided']} err={r['error']} interrupted={r['interrupted']} {s.get('ms', 0)/1000:.0f}s", flush=True)
    print("    answer:", r["answer"][:220].replace("\n", " "), flush=True)


async def main():
    sampler.start()
    store, agent = build()
    await agent.start()
    assert svc("wcncsvc") == "stopped", "test expects wcncsvc stopped at start"
    s1 = store.create_session()["id"]

    print(f"\n[{time.time()-T0:5.0f}s] 1. Auto, general question (no tools)")
    r = await agent.run_task("In one sentence: what does a DNS cache flush do?", model=MODEL, session_id=s1)
    summary(r)
    check("no tools for a general question", not r["tool_calls"] and not r["loaded"] and r["answer"])

    check("router loaded nothing for it", (r["routed"] or {}).get("domains") == [], r["routed"])

    print(f"\n[{time.time()-T0:5.0f}s] 2. Auto, live question (router -> storage, model -> disk_usage)")
    r = await agent.run_task("How much free space is on my drives?", model=MODEL, session_id=s1)
    summary(r)
    check("router loaded storage before the model ran", (r["routed"] or {}).get("domains") == ["storage"], r["routed"])
    check("model called disk_usage with no load_tools round", any(c["tool"] == "disk_usage" for c in r["tool_calls"])
          and r["load_tools_calls"] == 0)
    check("answer is grounded", r["grounded"])

    print(f"\n[{time.time()-T0:5.0f}s] 3. Follow-up in the same session (sticky tools: no reload)")
    r = await agent.run_task("And how full is it in percent?", model=MODEL, session_id=s1)
    summary(r)
    check("no load_tools round on the follow-up", r["load_tools_calls"] == 0)
    check("session remembers loaded toolsets", "storage" in store.session(s1)["loaded"], store.session(s1)["loaded"])

    print(f"\n[{time.time()-T0:5.0f}s] 3b. Multi-part request (two toolsets routed at once)")
    r = await agent.run_task("Check the CPU usage and the free disk space.", model=MODEL)
    summary(r)
    check("router loaded monitor + storage", set((r["routed"] or {}).get("domains", [])) == {"monitor", "storage"}, r["routed"])
    tools = {c["tool"] for c in r["tool_calls"]}
    check("both answered in one turn, no load_tools", "disk_usage" in tools and bool(tools & {"system_snapshot", "top_processes"})
          and r["load_tools_calls"] == 0, tools)

    print(f"\n[{time.time()-T0:5.0f}s] 3c. routing='llm' (no router: the model loads tools itself)")
    r = await agent.run_task("How much free space is on my drives?", model=MODEL, routing="llm")
    summary(r)
    check("no router step, model used load_tools", r["routed"] is None and r["load_tools_calls"] >= 1
          and any(c["tool"] == "disk_usage" for c in r["tool_calls"]))

    print(f"\n[{time.time()-T0:5.0f}s] 3d. routing='flat' (every tool loaded up front: benchmark baseline)")
    r = await agent.run_task("How much free space is on my drives?", model=MODEL, routing="flat")
    summary(r)
    check("no router, no load_tools, disk_usage called", r["routed"] is None and r["load_tools_calls"] == 0
          and any(c["tool"] == "disk_usage" for c in r["tool_calls"]))

    print(f"\n[{time.time()-T0:5.0f}s] 4. Storage card, question answerable from memory (hold / nudge / forced)")
    r = await agent.run_task("What is NTFS?", model=MODEL, mode="storage")
    summary(r)
    check("card turn ends grounded by a tool", r["grounded"] and r["tool_calls"])

    s2 = store.create_session()["id"]
    print(f"\n[{time.time()-T0:5.0f}s] 5. Services card: start wcncsvc, operator APPROVES")
    seen = []
    r = await agent.run_task("Start the wcncsvc service.", model=MODEL, mode="services", session_id=s2,
                             on_approval=lambda info: (seen.append(info), "approve")[1])
    summary(r)
    check("approval was requested for service_start", seen and seen[0]["tool"] == "service_start", seen[0]["summary"] if seen else "")
    check("service is running afterwards", svc("wcncsvc") == "running")

    print(f"\n[{time.time()-T0:5.0f}s] 6. Stop wcncsvc, operator DENIES")
    r = await agent.run_task("Now stop wcncsvc.", model=MODEL, mode="services", session_id=s2, on_approval=lambda i: "deny")
    summary(r)
    check("declined, service still running", any(c["approval"] == "declined" for c in r["tool_calls"]) and svc("wcncsvc") == "running")
    check("no nudge after a decision", not r["notices"], r["notices"])

    print(f"\n[{time.time()-T0:5.0f}s] 7. Hardline: stop RpcSs")
    r = await agent.run_task("Stop the RpcSs service.", model=MODEL, mode="services")
    summary(r)
    check("refused by hardline policy, no approval asked", any(c["tool"] == "service_stop" and c["decision"] == "DENY" for c in r["tool_calls"])
          and not any(c["approval"] for c in r["tool_calls"]))

    print(f"\n[{time.time()-T0:5.0f}s] 8. Cancel while the model is answering")
    s3 = store.create_session()["id"]
    q = agent.bus.subscribe(s3)
    await agent.send(s3, "Write a detailed 600-word essay on the history of Windows services.", mode="auto", model=MODEL)
    while True:
        ev = await q.get()
        if ev["type"] == "seg_delta":
            break
    await asyncio.sleep(2)
    await agent.cancel(s3)
    while (ev := await q.get())["type"] != "turn_end":
        pass
    agent.bus.unsubscribe(s3, q)
    check("turn ends as interrupted", ev["item"].get("interrupted"), f"{len(''.join(s['text'] for s in ev['item']['segments'] if s['kind']=='text'))} chars before stop")

    print(f"\n[{time.time()-T0:5.0f}s] 9. Pause for approval -> SERVER RESTART -> approve -> resumes")
    s4 = store.create_session()["id"]
    q = agent.bus.subscribe(s4)
    await agent.send(s4, "Stop wcncsvc.", mode="services", model=MODEL)
    while (ev := await q.get())["type"] not in ("paused", "turn_end"):
        pass
    agent.bus.unsubscribe(s4, q)
    check("run paused at the approval", ev["type"] == "paused")
    await agent.stop()                                     # simulate the server going down
    store, agent = build()                                 # brand new process state, same databases
    await agent.start()
    check("after restart the session is still paused", s4 in agent.paused)
    q = agent.bus.subscribe(s4)
    await agent.decide(s4, "approve")
    while (ev := await q.get())["type"] != "turn_end":
        pass
    agent.bus.unsubscribe(s4, q)
    item = ev["item"]
    print("    answer:", " ".join(s["text"] for s in item["segments"] if s["kind"] == "text")[:200].replace("\n", " "))
    check("resumed run finished and the service stopped", svc("wcncsvc") == "stopped" and not item.get("error"))

    print(f"\n[{time.time()-T0:5.0f}s] 10. Remote targets through the loopback transport")
    store.add_machine(label="loop-01", host="loop-01", os="windows", transport="local-ps", port=0)
    r = await agent.run_task("How much free disk space does loop-01 have?", model=MODEL)
    summary(r)
    check("ran on loop-01", any(c["machine"] == "loop-01" for c in r["tool_calls"]))
    r = await agent.run_task("Compare free disk space on this PC and loop-01.", model=MODEL, mode="storage")
    summary(r)
    machines = {c["machine"] for c in r["tool_calls"]}
    check("both machines checked", "loop-01" in machines and HOSTNAME in machines, machines)

    print(f"\n[{time.time()-T0:5.0f}s] 11. Embedding model missing -> falls back to the model's load_tools")
    await agent.stop()
    store, agent = build(embed_model="no-such-embedding-model")
    await agent.start()
    r = await agent.run_task("How much free space is on my drives?", model=MODEL)
    summary(r)
    check("router reports unavailable, turn still answered via load_tools",
          bool((r["routed"] or {}).get("error")) and r["load_tools_calls"] >= 1
          and any(c["tool"] == "disk_usage" for c in r["tool_calls"]), (r["routed"] or {}).get("error"))

    await agent.stop()
    sampler.stop()
    passed = sum(ok for _, ok in results)
    print(f"\n{passed}/{len(results)} checks passed in {time.time()-T0:.0f}s")
    for n, ok in results:
        if not ok:
            print("  FAILED:", n)


asyncio.run(main())
