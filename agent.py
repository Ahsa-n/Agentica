"""
Agentica agent — the orchestration loop, server side, as a LangGraph graph.

    START -> route -> model -> (tool -> [approval] -> tool ...) -> model -> ... -> finish -> END

  route     : stage 1 of the two-stage tool router (Auto mode): embeds the request and loads the
              matching toolsets before the model runs (router.py). Stage 2 is the model choosing
              among only those tools; load_tools stays available if the router missed something.
  model     : streams one model round from Ollama (thinking / text / tool calls)
  tool      : runs ONE queued tool call through Actions (policy engine)
  approval  : pauses the graph with interrupt() until the operator approves / denies
  finish    : stats, sticky toolsets, persist the transcript item

State is checkpointed (SQLite) after every node, so a run paused for approval survives a
server restart. Progress is streamed to browsers as events; the browser only renders.
`run_task()` drives a whole task without any browser (benchmarks, tests).
"""
from __future__ import annotations

import os

# Never send traces to LangSmith (LangChain's cloud service): Agentica stays local.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import asyncio
import copy
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, TypedDict

import aiosqlite
import httpx
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from hosts import get_password

log = logging.getLogger("agentica.agent")

MAX_ROUNDS = 8          # model rounds per turn
STICKY_TURNS = 3        # Auto mode: a loaded toolset stays loaded this many turns after its last use
LOCAL = "local"
RECURSION_LIMIT = 120   # graph steps per run (model + tool + approval nodes)
ROUTING_MODES = ("embed", "llm", "flat")
#   embed : stage 1 = embedding router, stage 2 = the model (default; load_tools as fallback)
#   llm   : no router, the model loads toolsets itself with load_tools (the previous behaviour)
#   flat  : every tool loaded up front (the benchmark's "flat baseline")


class AgentState(TypedDict, total=False):
    api: list            # model-facing message history (whole session)
    cur: dict            # transcript item being built this turn
    ctx: dict            # turn bookkeeping (round, queue, pending approval, ...)


class Busy(Exception):
    pass


class Run:
    """In-memory view of a session's activity (never persisted)."""

    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.cancel = False
        self.cur: dict | None = None
        self.status: str | None = None


class Bus:
    """Per-session event fan-out to connected browsers (and run_task)."""

    def __init__(self) -> None:
        self.subs: dict[str, set[asyncio.Queue]] = {}
        self.seq: dict[str, int] = {}

    def subscribe(self, sid: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subs.setdefault(sid, set()).add(q)
        return q

    def unsubscribe(self, sid: str, q: asyncio.Queue) -> None:
        self.subs.get(sid, set()).discard(q)

    def publish(self, sid: str, ev: dict) -> None:
        ev = copy.deepcopy(ev)            # freeze it: the objects it came from keep changing
        self.seq[sid] = self.seq.get(sid, 0) + 1
        ev["seq"] = self.seq[sid]
        for q in list(self.subs.get(sid, ())):
            q.put_nowait(ev)


# ============================================================================ helpers (ported 1:1 from the old client)

def machine_names(m: dict) -> list[str]:
    names = [m["label"], m["host"]]
    if not re.fullmatch(r"[\d.:]+", m["host"]) and "." in m["host"]:
        names.append(m["host"].split(".")[0])            # web-01.lab.local -> web-01
    return list(dict.fromkeys(n.lower() for n in names if n))


def mentioned_targets(text: str, machines: list[dict], local_host: str) -> list[str]:
    """Machines the operator names in a message. Deterministic string matching, no model involved."""
    low = text.lower()

    def said(name: str) -> bool:
        return re.search(rf"(^|[^\w.-]){re.escape(name)}(?=$|[^\w-])", low) is not None

    hits = [m["label"] for m in machines if any(said(n) for n in machine_names(m))]
    if said(local_host.lower()) or re.search(
            r"\b(this|my|the local) (pc|machine|computer|host|laptop|box)\b|\blocalhost\b", text, re.I):
        hits.append(LOCAL)
    return hits


def repair_history(api: list) -> None:
    """Close tool_calls that never got a result so the model-facing history stays well-formed."""
    for i in range(len(api) - 1, -1, -1):
        m = api[i]
        if m["role"] == "assistant" and m.get("tool_calls"):
            answered = sum(1 for x in api[i + 1:] if x["role"] == "tool")
            for c in m["tool_calls"][answered:]:
                api.append({"role": "tool", "tool_name": (c.get("function") or {}).get("name", "unknown"),
                            "content": json.dumps({"error": "Interrupted before this tool ran."})})
            return
        if m["role"] == "user":
            return


def parse_args(a: Any) -> dict:
    if a is None:
        return {}
    if isinstance(a, str):
        try:
            return json.loads(a) or {}
        except ValueError:
            return {}
    return a if isinstance(a, dict) else {}


# ============================================================================ agent

class Agent:
    def __init__(self, *, store, actions, tools: dict, toolsets: dict, ollama_url: str,
                 local_name: str, os_label: Callable[[], str], checkpoint_path: Path,
                 router=None, routing: str = "embed") -> None:
        self.store = store
        self.actions = actions
        self.tools = tools
        self.toolsets = toolsets
        self.ollama = ollama_url.rstrip("/")
        self.local_name = local_name
        self.os_label = os_label
        self.checkpoint_path = checkpoint_path
        self.router = router
        self.routing = routing if routing in ROUTING_MODES else "embed"
        self.bus = Bus()
        self.runs: dict[str, Run] = {}
        self.paused: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}
        self._caps: tuple[float, dict] = (0.0, {})
        self.graph = None
        self.conn = None
        self.http: httpx.AsyncClient | None = None
        self._sweeper: asyncio.Task | None = None
        self._warm: asyncio.Task | None = None

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(str(self.checkpoint_path))
        saver = AsyncSqliteSaver(self.conn)
        await saver.setup()
        self.saver = saver
        self.graph = self._build().compile(checkpointer=saver)
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(None, connect=5.0))
        await self._recover()
        self._sweeper = asyncio.create_task(self._sweep_expired())
        if self.router:
            self._warm = asyncio.create_task(self.router.warm())     # embeds the examples, loads the model

    async def stop(self) -> None:
        if self._sweeper:
            self._sweeper.cancel()
        for run in self.runs.values():
            if run.task and not run.task.done():
                run.task.cancel()
        if self.http:
            await self.http.aclose()
        if self.router:
            await self.router.close()
        if self.conn:
            await self.conn.close()

    def _cfg(self, sid: str) -> dict:
        return {"configurable": {"thread_id": sid}, "recursion_limit": RECURSION_LIMIT}

    def _lock(self, sid: str) -> asyncio.Lock:
        return self._locks.setdefault(sid, asyncio.Lock())

    async def _recover(self) -> None:
        """After a restart: paused runs stay paused (resumable); runs cut off mid-step are closed as interrupted."""
        for s in self.store.sessions(limit=1000):
            st = await self.graph.aget_state(self._cfg(s["id"]))
            if not st.next:
                continue
            if any(t.interrupts for t in st.tasks):
                self.paused.add(s["id"])
            else:
                await self._force_finish(s["id"], interrupted=True)

    # ------------------------------------------------------------------ events

    def emit(self, sid: str, type_: str, **data) -> None:
        self.bus.publish(sid, {"type": type_, **data})

    def set_status(self, sid: str, text: str | None) -> None:
        run = self.runs.get(sid)
        if run:
            run.status = text
        self.emit(sid, "status", text=text)

    # ------------------------------------------------------------------ prompt + tools (same logic as the old client)

    def toolset(self, tid: str | None) -> dict | None:
        return {"id": tid, **self.toolsets[tid]} if tid in self.toolsets else None

    def tools_in(self, ids) -> list:
        ids = set(ids)
        return [t for t in self.tools.values() if ids & set(t.toolsets)]

    def loadable(self) -> list[str]:
        return [i for i, s in self.toolsets.items() if not s.get("card_only")]

    def load_tools_schema(self, remaining: list[str]) -> dict:
        return {"type": "function", "function": {
            "name": "load_tools",
            "description": ("Load live system tools for the operator's machines. No tools are loaded by default. "
                            "Call this only when the request needs live data from a machine; answer general "
                            "questions directly. Domains: "
                            + "; ".join(f"{i} ({self.toolsets[i]['desc']})" for i in remaining) + "."),
            "parameters": {"type": "object", "properties": {"domains": {
                "type": "array", "items": {"type": "string", "enum": remaining}, "description": "Domains to load"}},
                "required": ["domains"]}}}

    def with_target(self, schema: dict, machines: list[dict]) -> dict:
        tool = self.tools.get(schema["function"]["name"])
        if not machines or (tool is not None and not getattr(tool, "uses_target", True)):
            return schema
        s = copy.deepcopy(schema)
        s["function"]["parameters"]["properties"]["target"] = {
            "type": "string", "enum": [LOCAL] + [m["label"] for m in machines],
            "description": "Machine to run on. Omit to use the current target."}
        return s

    def round_tools(self, card: dict | None, loaded: list[str], machines: list[dict]) -> list[dict]:
        if card:
            return [self.with_target(t.schema(), machines) for t in self.tools_in([card["id"]])]
        schemas = [self.with_target(t.schema(), machines) for t in self.tools_in(loaded)]
        remaining = [i for i in self.loadable() if i not in loaded]
        if remaining:
            schemas.insert(0, self.load_tools_schema(remaining))
        return schemas

    def machines_prompt(self, machines: list[dict], target: str | None, mentioned: list[str]) -> str:
        if not machines:
            return ""
        lines = [f"- {LOCAL}: this PC ({self.local_name})"]
        for m in machines:
            creds = bool(m.get("username")) and get_password(m["id"]) is not None
            st = ("connected" if m.get("last_ok") else "no credentials yet" if not creds
                  else "connection failing" if m.get("last_error") else "not tested")
            os_ = (m.get("os_info") or {}).get("os") or ("Windows" if m["os"] == "windows" else "Linux")
            lines.append(f"- {m['label']}: {m['host'] + ', ' if m['host'] != m['label'] else ''}{os_}, {st}")
        p = ("\nMachines (use these exact names for the `target` argument):\n" + "\n".join(lines) +
             f"\n- Current target: {target or LOCAL}. Every tool runs on the current target unless you pass `target`. "
             "Pass `target` only when the operator clearly means a different machine from this list (by name, address "
             "or an unambiguous description). If they mean a machine that is not listed, say so instead of guessing. "
             "Always say which machine your findings are from.")
        if len(mentioned) > 1:
            p += (f"\n- The latest message names several machines ({', '.join(mentioned)}): gather fresh evidence "
                  "from each one by passing `target`.")
        return p

    def system_prompt(self, card: dict | None, target: str | None, mentioned: list[str], machines: list[dict],
                      loaded: list[str] | None = None) -> str:
        p = (f'You are Agentica, an IT operations agent running locally on the operator\'s machine '
             f'(host "{self.local_name}", {self.os_label()}).\n'
             "- Never state a live value (usage, status, free space, processes, addresses) unless it came from a tool "
             "result in this conversation.\n"
             "- Tools that change the system (service_start, service_stop, service_restart) go through a policy engine: "
             "the operator may be asked to approve, and some actions are refused. When the operator asks for such a "
             "change, call the tool directly; do not ask for permission in text, the approval prompt handles that. Use "
             "the exact service name (look it up with service_status if needed). If a result says the operator declined "
             "or policy refused, do not retry; explain and suggest next steps. After a change, report whether it was "
             "verified (\"verified\" in the result).\n"
             "- For changes no tool supports, give the exact steps or commands the operator could run.\n"
             "- Be concise: lead with the finding, then the evidence. Use short Markdown tables for metrics and flag "
             "anything abnormal (CPU > 85%, memory > 90%, volume > 90% used, an automatic service that is stopped).")
        if not card:
            p += ("\n- Only the tools you were given are loaded. If the request needs live information those tools "
                  "cannot provide, first call load_tools with the relevant domain(s), then call the tools it loads. For "
                  "general IT questions (concepts, commands, how-tos) answer directly without loading tools.")
        else:
            names = ", ".join(t.name for t in self.tools_in([card["id"]]))
            p += (f"\n- The operator selected the {card['name']} card. Loaded tools: {names}. You MUST call at least one "
                  "of these tools to gather live evidence before answering. Never answer from memory. If none of them "
                  "can answer the request, say so and suggest another card.")
            if card["id"] == "troubleshoot":
                p += ("\n- Troubleshooting: gather evidence with several tools before concluding. Present the evidence, "
                      "the likely cause and recommended next steps; the operator makes the final call.")
        apps_ready = (card and card["id"] == "apps") or (not card and "apps" in (loaded or []))
        if apps_ready:
            p += ("\n- To open a program (\"open VS Code\") call app_open; to start watching one (\"monitor SQL Server\") "
                  "call app_register. Both ask the operator for approval themselves; any installed app can be opened, it "
                  "does not need to be monitored.")
        elif not card:
            p += ('\n- To open a program ("open VS Code"), start monitoring one, or check a monitored one: first call '
                  'load_tools with ["apps"], then use app_open / app_register / app_status. Loading tools never needs '
                  "the operator's permission; just call load_tools.")
        apps = self.store.apps()
        if apps:
            how = "check them with app_status"
            if not card and "apps" not in (loaded or []):
                how = 'first call load_tools with ["apps"], then check them with app_status'
            p += (f"\nMonitored applications ({how}): " +
                  ", ".join(f"{a['name']} (on {a['machine'] or 'this PC'})" for a in apps) + ".")
        return p + self.machines_prompt(machines, target, mentioned)

    async def capabilities(self, model: str) -> list[str]:
        ts, cache = self._caps
        if time.time() - ts > 30 or model not in cache:
            try:
                r = await self.http.get(f"{self.ollama}/api/tags", timeout=5)
                cache = {m["name"]: m.get("capabilities", []) for m in r.json().get("models", [])}
                self._caps = (time.time(), cache)
            except Exception:  # noqa: BLE001
                pass
        return cache.get(model, [])

    # ------------------------------------------------------------------ graph

    def _build(self) -> StateGraph:
        g = StateGraph(AgentState)
        g.add_node("route", self.node_route)
        g.add_node("model", self.node_model)
        g.add_node("tool", self.node_tool)
        g.add_node("approval", self.node_approval)
        g.add_node("finish", self.node_finish)
        g.add_edge(START, "route")
        g.add_edge("route", "model")
        g.add_conditional_edges("model", self._after_model, ["tool", "model", "finish"])
        g.add_conditional_edges("tool", self._after_tool, ["approval", "tool", "model", "finish"])
        g.add_conditional_edges("approval", self._after_tool, ["approval", "tool", "model", "finish"])
        g.add_edge("finish", END)
        return g

    @staticmethod
    def _after_model(s: AgentState) -> str:
        c = s["ctx"]
        return "finish" if c.get("done") else ("tool" if c.get("queue") else "model")

    @staticmethod
    def _after_tool(s: AgentState) -> str:
        c = s["ctx"]
        if c.get("done"):
            return "finish"
        if c.get("pending"):
            return "approval"
        return "tool" if c.get("queue") else "model"

    def _working(self, state: AgentState, sid: str):
        api, cur, ctx = copy.deepcopy(state["api"]), copy.deepcopy(state["cur"]), copy.deepcopy(state["ctx"])
        run = self.runs.get(sid)
        if run:
            run.cur = cur
        return api, cur, ctx, run

    @staticmethod
    def _abort(api: list, cur: dict, ctx: dict, *, interrupted=False, error=None, partial="") -> None:
        repair_history(api)
        api.append({"role": "assistant", "content": partial or "[no answer — turn ended early]"})
        if interrupted:
            cur["interrupted"] = True
        if error:
            cur["error"] = error
        ctx.update(done=True, queue=[], pending=None)

    # ---- route node: stage 1 of the two-stage router ---------------------------

    def machine_names(self, machines: list[dict]) -> list[str]:
        names = [self.local_name]
        for m in machines:
            names += machine_names(m)
        return names

    async def node_route(self, state: AgentState, config) -> AgentState:
        sid = config["configurable"]["thread_id"]
        api, cur, ctx, run = self._working(state, sid)
        if ctx["card"] or ctx.get("routing", "embed") != "embed" or not self.router or (run and run.cancel):
            return {"api": api, "cur": cur, "ctx": ctx}
        users = [m["content"] for m in api if m["role"] == "user" and not str(m["content"]).startswith("[policy]")]
        if not users:
            return {"api": api, "cur": cur, "ctx": ctx}
        self.set_status(sid, "Choosing tools…")
        d = await self.router.route(users[-1], previous=users[-2] if len(users) > 1 else None,
                                    names=self.machine_names(self.store.machines()))
        before = list(ctx["loaded"])
        new = [x for x in d.domains if x not in before]
        ctx["loaded"] = before + new
        ctx["routed"] = new
        seg = {"kind": "route", "via": "router", "domains": d.domains, "new": new, "kept": before,
               "tools": [t.name for t in self.tools_in(d.domains)], "scores": d.scores, "ms": d.ms,
               "context": d.context_used}
        if d.error:
            seg = {"kind": "route", "via": "router", "domains": [], "error": f"router unavailable ({d.error}); "
                   "the model loads tools itself", "kept": before}
        cur["segments"].append(seg)
        cur["route"] = {k: seg.get(k) for k in ("domains", "new", "scores", "ms", "error")}
        self.emit(sid, "seg_add", i=len(cur["segments"]) - 1, seg=seg)
        return {"api": api, "cur": cur, "ctx": ctx}

    # ---- model node -------------------------------------------------------------

    async def node_model(self, state: AgentState, config) -> AgentState:
        sid = config["configurable"]["thread_id"]
        api, cur, ctx, run = self._working(state, sid)
        if run and run.cancel:
            self._abort(api, cur, ctx, interrupted=True)
            return {"api": api, "cur": cur, "ctx": ctx}
        if ctx["round"] >= MAX_ROUNDS:
            cur["error"] = f"Stopped after {MAX_ROUNDS} rounds without a final answer."
            self._abort(api, cur, ctx)
            return {"api": api, "cur": cur, "ctx": ctx}
        ctx["round"] += 1

        card = self.toolset(ctx["card"])
        caps = await self.capabilities(ctx["model"])
        can_tools, can_think = "tools" in caps, "thinking" in caps
        machines = self.store.machines()
        tools = self.round_tools(card, ctx["loaded"], machines) if can_tools else []
        hold = bool(card) and can_tools and cur["evidence"] == 0 and not cur.get("decided")
        self.set_status(sid, "Working…" if ctx["round"] == 1 else "Reading results…")

        body = {"model": ctx["model"], "stream": True, "options": {"num_ctx": 8192},
                "messages": [{"role": "system", "content": self.system_prompt(card, ctx["target"], ctx["mentioned"], machines, ctx["loaded"])}]
                + api}
        if can_think:
            body["think"] = ctx["think"]
        if tools:
            body["tools"] = tools

        segs = cur["segments"]
        open_think = open_text = None
        t_think = 0.0
        content, calls = "", []

        def close_think():
            nonlocal open_think
            if open_think is not None:
                seg = segs[open_think]
                seg.update(ms=round((time.monotonic() - t_think) * 1000), done=True)
                self.emit(sid, "seg_set", i=open_think, seg=seg)
                open_think = None

        def close_text():
            nonlocal open_text
            if open_text is not None:
                seg = segs[open_text]
                seg["text"] = seg["text"].strip()
                self.emit(sid, "seg_set", i=open_text, seg=seg)
                open_text = None

        try:
            async with self.http.stream("POST", f"{self.ollama}/api/chat", json=body) as r:
                if r.status_code != 200:
                    detail = (await r.aread()).decode(errors="replace")
                    try:
                        detail = json.loads(detail).get("error", detail)
                    except ValueError:
                        pass
                    raise RuntimeError(f"Ollama: {detail}")
                async for line in r.aiter_lines():
                    if run and run.cancel:
                        break                               # closing the stream stops generation
                    if not line.strip():
                        continue
                    ch = json.loads(line)
                    if ch.get("error"):
                        raise RuntimeError(f"Ollama: {ch['error']}")
                    m = ch.get("message") or {}
                    if m.get("thinking"):
                        if open_think is None:
                            close_text()
                            segs.append({"kind": "thinking", "text": "", "ms": 0})
                            open_think = len(segs) - 1
                            t_think = time.monotonic()
                            self.emit(sid, "seg_add", i=open_think, seg=segs[open_think])
                            self.set_status(sid, None)
                        segs[open_think]["text"] += m["thinking"]
                        self.emit(sid, "seg_delta", i=open_think, text=m["thinking"])
                    if m.get("content"):
                        content += m["content"]
                        if hold:
                            self.set_status(sid, "Drafting…")
                        else:
                            if open_text is None:
                                close_think()
                                segs.append({"kind": "text", "text": ""})
                                open_text = len(segs) - 1
                                self.emit(sid, "seg_add", i=open_text, seg=segs[open_text])
                                self.set_status(sid, None)
                            segs[open_text]["text"] += m["content"]
                            self.emit(sid, "seg_delta", i=open_text, text=m["content"])
                    if m.get("tool_calls"):
                        calls.extend(m["tool_calls"])
                    if ch.get("done"):
                        ctx["tokens"] += ch.get("eval_count") or 0
                        ctx["ns"] += ch.get("eval_duration") or 0
        except Exception as e:  # noqa: BLE001
            close_think(); close_text()
            self._abort(api, cur, ctx, error=str(e) or type(e).__name__, partial="" if hold else content)
            return {"api": api, "cur": cur, "ctx": ctx}
        close_think(); close_text()

        if run and run.cancel:
            self._abort(api, cur, ctx, interrupted=True, partial="" if hold else content)
            return {"api": api, "cur": cur, "ctx": ctx}

        if calls:
            api.append({"role": "assistant", "content": content, "tool_calls": calls})
            ctx["queue"] = [{"name": (c.get("function") or {}).get("name", "unknown"),
                             "args": parse_args((c.get("function") or {}).get("arguments"))} for c in calls]
            return {"api": api, "cur": cur, "ctx": ctx}

        if hold and not ctx["nudged"]:
            ctx["nudged"] = True
            self._notice(sid, cur, "Answer held back: it wasn’t backed by a tool result. Asking the model to check "
                                   "live state first.")
            ctx["nudge_at"] = len(api)
            names = ", ".join(t.name for t in self.tools_in([card["id"]]))
            api.append({"role": "user", "content": f"[policy] You answered without calling a tool. This {card['name']} "
                                                   f"request requires live evidence. Call the most relevant tool now ({names})."})
            return {"api": api, "cur": cur, "ctx": ctx}

        if hold and not ctx["forced"]:
            ctx["forced"] = True
            d = card["default"]
            self._notice(sid, cur, f"Still no tool call. Running the {card['name']} card’s default check so the answer "
                                   "is grounded.")
            where = ctx["mentioned"] or [None]
            args_for = (lambda t: {**d["args"], "target": t} if t else dict(d["args"]))
            api.append({"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": d["name"], "arguments": args_for(t)}} for t in where]})
            ctx["queue"] = [{"name": d["name"], "args": args_for(t), "auto": True} for t in where]
            return {"api": api, "cur": cur, "ctx": ctx}

        if hold:     # last resort: shown, flagged as not verified by a tool
            segs.append({"kind": "text", "text": content.strip()})
            self.emit(sid, "seg_add", i=len(segs) - 1, seg=segs[-1])
        api.append({"role": "assistant", "content": content})
        ctx["done"] = True
        return {"api": api, "cur": cur, "ctx": ctx}

    def _notice(self, sid: str, cur: dict, text: str) -> None:
        cur["segments"].append({"kind": "notice", "text": text})
        self.emit(sid, "seg_add", i=len(cur["segments"]) - 1, seg=cur["segments"][-1])

    # ---- tool node --------------------------------------------------------------

    def _settle_tool(self, sid: str, api: list, cur: dict, ctx: dict, i: int, call: dict, res: dict) -> None:
        seg = cur["segments"][i]
        seg["res"] = res
        ok = res.get("decision") == "ALLOW" and not res.get("error")
        seg["status"] = "done" if ok else "failed"
        if ok:
            cur["evidence"] += 1
        elif seg.get("approval") or res.get("blocked_by") in ("policy", "state"):
            cur["decided"] = cur.get("decided", 0) + 1
        if not ctx["card"]:
            sets = getattr(self.tools.get(call["name"]), "toolsets", [])
            ctx["used"] = list(dict.fromkeys(ctx["used"] + [x for x in sets if x in ctx["loaded"]]))
        payload = res["result"] if res.get("result") is not None else {"decision": res.get("decision"), "error": res.get("error")}
        if (seg.get("approval") or {}).get("state") == "declined" and isinstance(payload, dict):
            payload = {**payload, "note": "The operator declined. Do not retry this action unless they ask again."}
        api.append({"role": "tool", "tool_name": call["name"], "content": json.dumps(payload)})
        ctx["queue"].pop(0)
        self.emit(sid, "seg_set", i=i, seg=seg)

    async def node_tool(self, state: AgentState, config) -> AgentState:
        sid = config["configurable"]["thread_id"]
        api, cur, ctx, run = self._working(state, sid)
        if run and run.cancel:
            self._abort(api, cur, ctx, interrupted=True)
            return {"api": api, "cur": cur, "ctx": ctx}
        call = ctx["queue"][0]
        card = self.toolset(ctx["card"])

        if not card and call["name"] == "load_tools":
            want = call["args"].get("domains", call["args"].get("domain", []))
            want = want if isinstance(want, list) else [want]
            valid = [d for d in want if d in self.loadable()]
            ctx["loaded"] = list(dict.fromkeys(ctx["loaded"] + valid))
            ctx["used"] = list(dict.fromkeys(ctx["used"] + valid))
            if valid:
                seg = {"kind": "route", "domains": valid, "tools": [t.name for t in self.tools_in(valid)]}
                payload = {"loaded": valid, "now_available": [t.name for t in self.tools_in(ctx["loaded"])]}
            else:
                seg = {"kind": "route", "domains": [], "error": f"unknown domain {json.dumps(want)}"}
                payload = {"error": seg["error"], "valid_domains": self.loadable()}
            cur["segments"].append(seg)
            self.emit(sid, "seg_add", i=len(cur["segments"]) - 1, seg=seg)
            api.append({"role": "tool", "tool_name": "load_tools", "content": json.dumps(payload)})
            ctx["queue"].pop(0)
            return {"api": api, "cur": cur, "ctx": ctx}

        seg = {"kind": "tool", "name": call["name"], "args": call["args"], "auto": bool(call.get("auto")),
               "status": "running", "res": None}
        cur["segments"].append(seg)
        i = len(cur["segments"]) - 1
        self.emit(sid, "seg_add", i=i, seg=seg)
        self.set_status(sid, f"Running {call['name']}…")
        scope = [card["id"]] if card else ctx["loaded"]
        res, _ = await self.actions.request(call["name"], call["args"], scope, ctx["target"] or LOCAL, sid)

        if res.get("decision") == "CONFIRM" and res.get("approval_id"):
            seg.update(status="pending", res=res, approval={
                "id": res["approval_id"], "state": "pending", "risk": res.get("risk"), "risk_label": res.get("risk_label"),
                "summary": res.get("summary"), "reasons": res.get("reasons", []), "expires": res.get("expires")})
            ctx["pending"] = {"approval_id": res["approval_id"], "seg": i}
            self.emit(sid, "seg_set", i=i, seg=seg)
            self.set_status(sid, "Waiting for your approval…")
            return {"api": api, "cur": cur, "ctx": ctx}

        self._settle_tool(sid, api, cur, ctx, i, call, res)
        return {"api": api, "cur": cur, "ctx": ctx}

    # ---- approval node: pauses the graph ---------------------------------------

    async def node_approval(self, state: AgentState, config) -> AgentState:
        # Everything before interrupt() runs again on resume, so it must have no side effects.
        pending = state["ctx"]["pending"]
        action = interrupt({"approval_id": pending["approval_id"]})

        sid = config["configurable"]["thread_id"]
        api, cur, ctx, run = self._working(state, sid)
        seg = cur["segments"][pending["seg"]]
        if action == "approve":
            self.set_status(sid, f"Running {seg['name']}…")
        res, st = await self.actions.settle(pending["approval_id"], action)
        seg["approval"] = {**seg["approval"], "state": st, "decided": round(time.time() * 1000)}
        ctx["pending"] = None
        self._settle_tool(sid, api, cur, ctx, pending["seg"], ctx["queue"][0], res)
        if action == "cancel":
            self._abort(api, cur, ctx, interrupted=True)
        return {"api": api, "cur": cur, "ctx": ctx}

    # ---- finish node ------------------------------------------------------------

    def _finalize(self, sid: str, api: list, cur: dict, ctx: dict) -> None:
        at = ctx.get("nudge_at")
        if at is not None and at < len(api) and str(api[at].get("content", "")).startswith("[policy]"):
            api.pop(at)
        cur["segments"] = [s for s in cur["segments"]
                           if not (s["kind"] in ("thinking", "text") and not s.get("text", "").strip())]
        for s in cur["segments"]:
            if s["kind"] == "thinking":
                s["done"] = True
        tps = ctx["tokens"] / (ctx["ns"] / 1e9) if ctx["ns"] else None
        cur["stats"] = {"tokens": ctx["tokens"], "tps": tps, "ms": round((time.time() - ctx["t0"]) * 1000),
                        "think": ctx.get("can_think", False) and ctx["think"], "model": ctx["model"]}
        if not ctx["card"] and ctx.get("routing") != "flat":
            sess = self.store.session(sid) or {}
            prev = sess.get("loaded") or {}
            routed = set(ctx.get("routed") or [])
            nxt = {}
            for tid in ctx["loaded"]:
                if tid in ctx["used"]:
                    left = STICKY_TURNS
                elif tid in routed:           # the router guessed it, nothing used it: don't carry it over
                    left = 0
                else:
                    left = prev.get(tid, STICKY_TURNS) - 1
                if left > 0:
                    nxt[tid] = left
            self.store.update_session(sid, loaded=nxt)
        else:
            self.store.update_session(sid)
        self.store.put_item(sid, cur)

    async def node_finish(self, state: AgentState, config) -> AgentState:
        sid = config["configurable"]["thread_id"]
        api, cur, ctx, run = self._working(state, sid)
        self._finalize(sid, api, cur, ctx)
        return {"api": api, "cur": cur, "ctx": ctx}

    async def _force_finish(self, sid: str, *, interrupted=False, error=None) -> None:
        """Close a run that cannot continue (crash, restart mid-step) and record it."""
        cfg = self._cfg(sid)
        st = await self.graph.aget_state(cfg)
        if not st.values.get("cur"):
            return
        api, cur, ctx = copy.deepcopy(st.values["api"]), copy.deepcopy(st.values["cur"]), copy.deepcopy(st.values["ctx"])
        self._abort(api, cur, ctx, interrupted=interrupted, error=error)
        self._finalize(sid, api, cur, ctx)
        await self.graph.aupdate_state(cfg, {"api": api, "cur": cur, "ctx": ctx}, as_node="finish")
        self.paused.discard(sid)

    # ------------------------------------------------------------------ driving runs

    async def _drive(self, sid: str, payload) -> None:
        cfg = self._cfg(sid)
        run = self.runs[sid]
        st = None
        try:
            try:
                await self.graph.ainvoke(payload, cfg)
            except Exception as e:  # noqa: BLE001 - a bug in a node must not leave the session stuck
                log.exception("agent run failed")
                await self._force_finish(sid, error=f"Internal error: {type(e).__name__}: {e}")
            st = await self.graph.aget_state(cfg)
            if st.next:
                self.paused.add(sid)
            else:
                self.paused.discard(sid)
                await self._prune(sid)
        finally:
            run.task = None
            run.status = None
            run.cancel = False
            if sid not in self.paused:
                self.runs.pop(sid, None)
        if st is None:
            return
        if st.next:
            self.emit(sid, "paused", cur=st.values.get("cur"), session=self.session_view(sid))
        else:
            self.emit(sid, "turn_end", item=st.values.get("cur"), session=self.session_view(sid))

    def session_view(self, sid: str) -> dict | None:
        s = self.store.session(sid)
        if not s:
            return None
        state = "running" if (self.runs.get(sid) and self.runs[sid].task) else "paused" if sid in self.paused else "idle"
        return {"id": s["id"], "title": s["title"], "created": s["created"], "updated": s["updated"],
                "target": s["target"], "loaded": s["loaded"], "state": state}

    async def busy(self, sid: str) -> bool:
        run = self.runs.get(sid)
        return bool(run and run.task and not run.task.done()) or sid in self.paused

    async def send(self, sid: str, text: str, *, mode: str = "auto", think: bool = False, model: str,
                   routing: str | None = None) -> dict:
        async with self._lock(sid):
            sess = self.store.session(sid)
            if not sess:
                raise KeyError(sid)
            if await self.busy(sid):
                raise Busy("This session is still working on the previous request.")
            text = text.strip()
            machines = self.store.machines()
            hits = mentioned_targets(text, machines, self.local_name)
            if len(hits) == 1:
                self.store.update_session(sid, target=None if hits[0] == LOCAL else hits[0])
            if not sess["title"]:
                self.store.update_session(sid, title=re.sub(r"\s+", " ", text)[:60])
            sess = self.store.session(sid)
            card = self.toolset(mode) if mode in self.toolsets else None
            now_ms = round(time.time() * 1000)
            user_item = {"id": uuid.uuid4().hex, "type": "user", "text": text, "scope": card["id"] if card else None,
                         "t": now_ms, "targets": hits}
            self.store.put_item(sid, user_item)
            caps = await self.capabilities(model)
            cur = {"id": uuid.uuid4().hex, "type": "agent", "t": now_ms, "segments": [],
                   "scope": card["id"] if card else None, "evidence": 0, "decided": 0}
            ctx = {"card": card["id"] if card else None, "round": 0, "nudged": False, "forced": False, "nudge_at": None,
                   "queue": [], "pending": None, "model": model, "think": bool(think), "can_think": "thinking" in caps,
                   "t0": time.time(), "tokens": 0, "ns": 0, "target": sess["target"],
                   "mentioned": hits if len(hits) > 1 else [],
                   "loaded": [] if card else list(sess["loaded"].keys()), "used": [], "done": False,
                   "routing": routing if routing in ROUTING_MODES else self.routing, "routed": []}
            if not card and ctx["routing"] == "flat":
                ctx["loaded"] = self.loadable()
            prev = await self.graph.aget_state(self._cfg(sid))
            api = list(prev.values.get("api", [])) + [{"role": "user", "content": text}]

            run = Run()
            run.cur = cur
            self.runs[sid] = run
            self.emit(sid, "user", item=user_item)
            self.emit(sid, "session", session=self.session_view(sid))
            self.emit(sid, "item_start", item=cur)
            run.task = asyncio.create_task(self._drive(sid, {"api": api, "cur": cur, "ctx": ctx}))
            return user_item

    async def decide(self, sid: str, action: str) -> None:
        """Resume a run paused for approval. action: approve | deny | expire | cancel."""
        async with self._lock(sid):
            if sid not in self.paused:
                raise KeyError("No approval is pending in this session.")
            self.paused.discard(sid)
            run = self.runs.get(sid) or Run()
            self.runs[sid] = run
            st = await self.graph.aget_state(self._cfg(sid))
            run.cur = copy.deepcopy(st.values.get("cur"))
            run.task = asyncio.create_task(self._drive(sid, Command(resume=action)))

    async def cancel(self, sid: str) -> None:
        run = self.runs.get(sid)
        if run and run.task and not run.task.done():
            run.cancel = True
            return
        if sid in self.paused:
            await self.decide(sid, "cancel")

    async def view(self, sid: str) -> dict:
        """Snapshot for a browser that (re)connects: finished items + the live item, consistent with event seq."""
        st = await self.graph.aget_state(self._cfg(sid))
        sess = self.session_view(sid)
        run = self.runs.get(sid)
        live = None
        if run and run.task:
            live = copy.deepcopy(run.cur)
        elif sid in self.paused:
            live = copy.deepcopy(st.values.get("cur"))
        return {"session": sess, "items": self.store.items(sid), "live": live,
                "status": run.status if run else None, "seq": self.bus.seq.get(sid, 0)}

    async def delete(self, sid: str) -> None:
        if await self.busy(sid):
            raise Busy("Stop the running request first.")
        await self.saver.adelete_thread(sid)
        self.store.delete_session(sid)
        self.runs.pop(sid, None)

    async def _prune(self, sid: str) -> None:
        """Keep only the latest checkpoint of a finished turn (older ones are history we never read)."""
        try:
            keep = "(SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? ORDER BY checkpoint_id DESC LIMIT 1)"
            await self.conn.execute(f"DELETE FROM writes WHERE thread_id = ? AND checkpoint_id NOT IN {keep}", (sid, sid))
            await self.conn.execute(f"DELETE FROM checkpoints WHERE thread_id = ? AND checkpoint_id NOT IN {keep}", (sid, sid))
            await self.conn.commit()
        except Exception:  # noqa: BLE001
            log.exception("checkpoint prune failed")

    async def _sweep_expired(self) -> None:
        while True:
            await asyncio.sleep(15)
            for sid in list(self.paused):
                try:
                    st = await self.graph.aget_state(self._cfg(sid))
                    pending = (st.values.get("ctx") or {}).get("pending")
                    rec = self.store.get_approval(pending["approval_id"]) if pending else None
                    if rec and rec["status"] == "expired":
                        await self.decide(sid, "expire")
                except Exception:  # noqa: BLE001
                    log.exception("expiry sweep failed")

    # ------------------------------------------------------------------ headless (benchmarks, tests)

    async def run_task(self, prompt: str, *, model: str, mode: str = "auto", think: bool = False,
                       target: str | None = None, session_id: str | None = None, routing: str | None = None,
                       on_approval: Callable[[dict], str] | None = None, timeout: float = 900) -> dict:
        """Run one request to completion without a browser. on_approval(info) -> 'approve' | 'deny' (default deny)."""
        sid = session_id or self.store.create_session(target)["id"]
        q = self.bus.subscribe(sid)
        t0 = time.time()
        try:
            await self.send(sid, prompt, mode=mode, think=think, model=model, routing=routing)
            while True:
                ev = await asyncio.wait_for(q.get(), timeout=max(1.0, timeout - (time.time() - t0)))
                if ev["type"] == "paused":
                    seg = next(s for s in ev["cur"]["segments"] if s.get("approval", {}).get("state") == "pending")
                    info = {"tool": seg["name"], "args": seg["args"], **seg["approval"]}
                    await self.decide(sid, (on_approval or (lambda _: "deny"))(info))
                elif ev["type"] == "turn_end":
                    item = ev["item"]
                    break
        finally:
            self.bus.unsubscribe(sid, q)
        segs = item["segments"]
        return {
            "session": sid,
            "answer": "\n\n".join(s["text"] for s in segs if s["kind"] == "text"),
            "tool_calls": [{"tool": s["name"], "args": s["args"], "auto": s.get("auto", False),
                            "decision": (s.get("res") or {}).get("decision"),
                            "machine": (s.get("res") or {}).get("target"),
                            "approval": (s.get("approval") or {}).get("state"),
                            "error": (s.get("res") or {}).get("error")} for s in segs if s["kind"] == "tool"],
            "loaded": list(dict.fromkeys(d for s in segs if s["kind"] == "route" for d in s.get("domains", []))),
            "routed": item.get("route"),
            "load_tools_calls": sum(1 for s in segs if s["kind"] == "route" and s.get("via") != "router"),
            "notices": [s["text"] for s in segs if s["kind"] == "notice"],
            "grounded": item.get("evidence", 0) > 0, "decided": item.get("decided", 0),
            "error": item.get("error"), "interrupted": item.get("interrupted", False),
            "stats": item.get("stats"), "item": item,
        }
