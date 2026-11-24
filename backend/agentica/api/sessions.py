"""Sessions API — chat, streaming, history, approval, cancel."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel
from sqlalchemy import text
from sse_starlette.sse import EventSourceResponse

from agentica.agent.graph import TURN_RESET, get_graph, run_config_for
from agentica.agent.state import AgentState, RunConfig, ToolCall
from agentica.config.logging import get_logger
from agentica.db.engine import get_session_factory

router = APIRouter()
logger = get_logger(__name__)

# Track active runs per session (session_id → task)
_active_runs: dict[str, asyncio.Task] = {}

_TITLE_MAX = 60


class MessageRequest(BaseModel):
    content: str
    routing_mode: str = "routed"
    force_categories: list[str] = []


class ApprovalRequest(BaseModel):
    approved: bool


def _as_tool_call(obj: Any) -> ToolCall | None:
    if obj is None:
        return None
    if isinstance(obj, ToolCall):
        return obj
    if isinstance(obj, dict):
        return ToolCall.model_validate(obj)
    return None


def _risk_tier(tool_name: str) -> str | None:
    from agentica.tools.registry import registry
    tool = registry.get(tool_name)
    return tool.spec.risk_tier.value if tool else None


def _tool_call_payload(tc: ToolCall) -> dict:
    return {
        "risk_tier": _risk_tier(tc.tool_name),
        "call_id": tc.call_id,
        "tool": tc.tool_name,
        "args": tc.args,
        "target_id": tc.target_id,
        "decision": tc.policy_decision,
        "reason": tc.policy_reason,
        "rule_id": tc.policy_rule_id,
        "result": tc.result if tc.result is not None else ({"error": tc.error} if tc.error else None),
        "duration_ms": tc.duration_ms,
    }


async def _touch_session(session_id: str, first_message: str | None = None) -> None:
    """Bump updated_at; on the first message, replace the placeholder title."""
    async with get_session_factory()() as db:
        if first_message:
            title = " ".join(first_message.split())
            if len(title) > _TITLE_MAX:
                title = title[: _TITLE_MAX - 1].rstrip() + "…"
            await db.execute(
                text(
                    "UPDATE sessions SET title = :t, updated_at = now() "
                    "WHERE id = :id AND (title IS NULL OR title = 'New Session')"
                ),
                {"id": session_id, "t": title},
            )
        await db.execute(text("UPDATE sessions SET updated_at = now() WHERE id = :id"), {"id": session_id})
        await db.commit()


@router.get("/sessions")
async def list_sessions() -> list[dict]:
    async with get_session_factory()() as session:
        rows = (await session.execute(
            text("SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 50")
        )).fetchall()
        return [
            {"id": str(r[0]), "title": r[1], "created_at": r[2].isoformat(), "updated_at": r[3].isoformat()}
            for r in rows
        ]


@router.post("/sessions")
async def create_session() -> dict:
    session_id = str(uuid.uuid4())
    async with get_session_factory()() as db:
        await db.execute(
            text("INSERT INTO sessions (id, title) VALUES (:id, :title)"),
            {"id": session_id, "title": "New Session"}
        )
        await db.commit()
    return {"id": session_id}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    async with get_session_factory()() as db:
        await db.execute(text("DELETE FROM sessions WHERE id = :id"), {"id": session_id})
        await db.commit()
    return {"ok": True}


@router.get("/sessions/{session_id}/messages")
async def get_history(session_id: str) -> list[dict]:
    """Rebuild the chat transcript (with tool calls) from the LangGraph checkpoint."""
    graph = await get_graph()
    snapshot = await graph.aget_state(run_config_for(session_id))
    values = snapshot.values or {}
    messages = values.get("messages", []) or []

    known: dict[str, ToolCall] = {}
    for raw in values.get("tool_calls_history", []) or []:
        tc = _as_tool_call(raw)
        if tc:
            known[tc.call_id] = tc
    pending = _as_tool_call(values.get("pending_tool_call"))
    awaiting = pending is not None and "approval" in (snapshot.next or ())
    if pending:
        known.setdefault(pending.call_id, pending)

    out: list[dict] = []
    turn: dict | None = None

    def flush() -> None:
        nonlocal turn
        if turn and (turn["content"] or turn["toolCalls"]):
            out.append(turn)
        turn = None

    for m in messages:
        if isinstance(m, HumanMessage):
            flush()
            out.append({"role": "user", "content": m.content})
            turn = {"role": "assistant", "content": "", "toolCalls": []}
        elif isinstance(m, AIMessage):
            if turn is None:
                turn = {"role": "assistant", "content": "", "toolCalls": []}
            if m.tool_calls:
                for c in m.tool_calls[:1]:  # the graph executes only the first tool call
                    cid = c.get("id") or ""
                    tc = known.get(cid)
                    entry = _tool_call_payload(tc) if tc else {
                        "call_id": cid, "tool": c.get("name"), "args": c.get("args", {}),
                    }
                    if awaiting and pending and cid == pending.call_id:
                        entry["awaitingApproval"] = True
                    turn["toolCalls"].append(entry)
            elif m.content:
                turn["content"] = m.content if isinstance(m.content, str) else json.dumps(m.content)
        elif isinstance(m, ToolMessage) and turn is not None:
            for entry in turn["toolCalls"]:
                if entry["call_id"] == m.tool_call_id and entry.get("result") is None:
                    try:
                        entry["result"] = json.loads(m.content)
                    except (TypeError, json.JSONDecodeError):
                        entry["result"] = {"data": m.content}
    flush()
    return out


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: MessageRequest, request: Request):
    """Stream SSE events for a new message."""
    if session_id in _active_runs and not _active_runs[session_id].done():
        raise HTTPException(status_code=409, detail="A run is already active for this session.")

    graph = await get_graph()
    config = run_config_for(session_id)
    run_config = RunConfig(
        session_id=session_id,
        routing_mode=body.routing_mode,
        force_categories=body.force_categories,
    )

    snapshot = await graph.aget_state(config)
    is_first = not (snapshot.values or {}).get("messages")
    await _touch_session(session_id, body.content if is_first else None)

    async def event_stream() -> AsyncIterator[dict]:
        try:
            yield {"event": "run_start", "data": json.dumps({"session_id": session_id})}

            # Reset per-turn fields so state from the previous turn (final answer, step
            # counters, pending call) cannot leak into this one. Messages accumulate.
            state_input = {
                **TURN_RESET,
                "messages": [HumanMessage(content=body.content)],
                "run_config": run_config,
            }

            # stream_mode="values" yields the full state after every step, so each
            # event is de-duplicated to fire once per turn / per tool call.
            route_sent = False
            sent: dict[str, set[str]] = {"policy": set(), "approval": set()}
            last_result: dict[str, str] = {}
            final_sent = False

            async for chunk in graph.astream(state_input, config=config, stream_mode="values"):
                if not isinstance(chunk, dict) or ("__interrupt__" in chunk and len(chunk) == 1):
                    continue
                state = AgentState.model_validate(chunk)

                if state.routed_categories and not route_sent:
                    route_sent = True
                    yield {"event": "route", "data": json.dumps({"categories": state.routed_categories})}

                tc = state.pending_tool_call
                if tc:
                    if tc.policy_decision and tc.call_id not in sent["policy"]:
                        sent["policy"].add(tc.call_id)
                        yield {
                            "event": "policy_decision",
                            "data": json.dumps({
                                "call_id": tc.call_id,
                                "tool": tc.tool_name,
                                "args": tc.args,
                                "target_id": tc.target_id,
                                "decision": tc.policy_decision,
                                "reason": tc.policy_reason,
                                "rule_id": tc.policy_rule_id,
                            })
                        }
                    if tc.policy_decision == "confirm" and tc.call_id not in sent["approval"] and not tc.result:
                        sent["approval"].add(tc.call_id)
                        yield {
                            "event": "approval_required",
                            "data": json.dumps({
                                "call_id": tc.call_id,
                                "tool": tc.tool_name,
                                "args": tc.args,
                                "target_id": tc.target_id,
                                "policy_reason": tc.policy_reason,
                                "rule_id": tc.policy_rule_id,
                                "risk_tier": _risk_tier(tc.tool_name),
                            })
                        }
                    if tc.result is not None or tc.error:
                        result = tc.result if tc.result is not None else {"error": tc.error}
                        # Re-emitted when the result changes, e.g. verify() adding "verified".
                        fingerprint = json.dumps(result, default=str, sort_keys=True)
                        if last_result.get(tc.call_id) != fingerprint:
                            last_result[tc.call_id] = fingerprint
                            yield {
                                "event": "tool_end",
                                "data": json.dumps({
                                    "call_id": tc.call_id,
                                    "tool": tc.tool_name,
                                    "args": tc.args,
                                    "target_id": tc.target_id,
                                    "duration_ms": tc.duration_ms,
                                    "result": result,
                                }, default=str)
                            }

                if state.final_answer and not final_sent:
                    final_sent = True
                    yield {"event": "token", "data": json.dumps({"text": state.final_answer})}
                    yield {"event": "final", "data": json.dumps({"answer": state.final_answer})}

            yield {"event": "run_end", "data": json.dumps({})}

        except asyncio.CancelledError:
            yield {"event": "error", "data": json.dumps({"message": "Run cancelled."})}
        except Exception as e:
            logger.error("stream_error", error=str(e))
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    async def sse_generator():
        async for evt in event_stream():
            if await request.is_disconnected():
                break
            yield evt

    return EventSourceResponse(sse_generator())


@router.post("/sessions/{session_id}/approvals/{call_id}")
async def submit_approval(session_id: str, call_id: str, body: ApprovalRequest) -> dict:
    """Resume a run waiting for approval; return the tool outcome and the final answer."""
    graph = await get_graph()
    config = run_config_for(session_id)
    from langgraph.types import Command

    snapshot = await graph.aget_state(config)
    pending = _as_tool_call((snapshot.values or {}).get("pending_tool_call"))
    if "approval" not in (snapshot.next or ()) or not pending or pending.call_id != call_id:
        raise HTTPException(status_code=409, detail="This action is no longer awaiting approval.")

    try:
        result = await graph.ainvoke(Command(resume={"approved": body.approved}), config=config)
    except Exception as e:
        logger.error("approval_error", error=str(e))
        return {"ok": False, "answer": "", "approved": body.approved, "error": str(e)}

    values = result if isinstance(result, dict) else {}
    tool_call = None
    for raw in values.get("tool_calls_history", []) or []:
        tc = _as_tool_call(raw)
        if tc and tc.call_id == call_id:
            tool_call = _tool_call_payload(tc)
    if tool_call is None:
        tool_call = _tool_call_payload(pending.model_copy(update={
            "error": "Denied by administrator." if not body.approved else "Execution failed."
        }))

    # The resumed run may have stopped at another approval (e.g. a follow-up action).
    after = await graph.aget_state(config)
    next_approval = None
    nxt = _as_tool_call((after.values or {}).get("pending_tool_call"))
    if "approval" in (after.next or ()) and nxt:
        next_approval = {**_tool_call_payload(nxt), "awaitingApproval": True}

    await _touch_session(session_id)
    return {
        "ok": True,
        "approved": body.approved,
        "answer": values.get("final_answer") or "",
        "tool_call": tool_call,
        "next_approval": next_approval,
    }


@router.post("/sessions/{session_id}/cancel")
async def cancel_run(session_id: str) -> dict:
    task = _active_runs.get(session_id)
    if task and not task.done():
        task.cancel()
        return {"ok": True, "cancelled": True}
    return {"ok": True, "cancelled": False}
