"""Sessions API — chat, streaming, approval, cancel."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agentica.agent.graph import get_graph
from agentica.agent.state import AgentState, RunConfig
from agentica.config.logging import get_logger
from agentica.db.engine import get_session_factory
from agentica.db.models import Session as DBSession

router = APIRouter()
logger = get_logger(__name__)

# Track active runs per session (session_id → task)
_active_runs: dict[str, asyncio.Task] = {}


class MessageRequest(BaseModel):
    content: str
    routing_mode: str = "routed"
    force_categories: list[str] = []


class ApprovalRequest(BaseModel):
    approved: bool


@router.get("/sessions")
async def list_sessions() -> list[dict]:
    async with get_session_factory()() as session:
        from sqlalchemy import text
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
        from sqlalchemy import text
        await db.execute(
            text("INSERT INTO sessions (id, title) VALUES (:id, :title)"),
            {"id": session_id, "title": "New Session"}
        )
        await db.commit()
    return {"id": session_id}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    async with get_session_factory()() as db:
        from sqlalchemy import text
        await db.execute(text("DELETE FROM sessions WHERE id = :id"), {"id": session_id})
        await db.commit()
    return {"ok": True}


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: str, body: MessageRequest, request: Request):
    """Stream SSE events for a new message."""
    if session_id in _active_runs and not _active_runs[session_id].done():
        raise HTTPException(status_code=409, detail="A run is already active for this session.")

    graph = await get_graph()
    config = {"configurable": {"thread_id": session_id}}
    run_config = RunConfig(
        session_id=session_id,
        routing_mode=body.routing_mode,
        force_categories=body.force_categories,
    )

    async def event_stream() -> AsyncIterator[dict]:
        try:
            yield {"event": "run_start", "data": json.dumps({"session_id": session_id})}

            state_input = {
                "messages": [HumanMessage(content=body.content)],
                "run_config": run_config,
            }

            async for chunk in graph.astream(state_input, config=config, stream_mode="values"):
                state = AgentState.model_validate(chunk)

                # Emit route event
                if state.routed_categories:
                    yield {"event": "route", "data": json.dumps({"categories": state.routed_categories})}

                # Emit tool events
                tc = state.pending_tool_call
                if tc:
                    if tc.policy_decision:
                        yield {
                            "event": "policy_decision",
                            "data": json.dumps({
                                "call_id": tc.call_id,
                                "tool": tc.tool_name,
                                "decision": tc.policy_decision,
                                "reason": tc.policy_reason,
                                "rule_id": tc.policy_rule_id,
                            })
                        }
                    if tc.policy_decision == "confirm":
                        yield {
                            "event": "approval_required",
                            "data": json.dumps({
                                "call_id": tc.call_id,
                                "tool": tc.tool_name,
                                "args": tc.args,
                                "target_id": tc.target_id,
                                "policy_reason": tc.policy_reason,
                            })
                        }
                    if tc.result:
                        yield {
                            "event": "tool_end",
                            "data": json.dumps({
                                "call_id": tc.call_id,
                                "tool": tc.tool_name,
                                "duration_ms": tc.duration_ms,
                                "result": tc.result,
                            })
                        }

                # Emit final answer tokens
                if state.final_answer:
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
    """Resume a run waiting for approval."""
    graph = await get_graph()
    config = {"configurable": {"thread_id": session_id}}
    from langgraph.types import Command
    await graph.aupdate_state(config, None, as_node="approval")
    await graph.ainvoke(Command(resume={"approved": body.approved}), config=config)
    return {"ok": True}


@router.post("/sessions/{session_id}/cancel")
async def cancel_run(session_id: str) -> dict:
    task = _active_runs.get(session_id)
    if task and not task.done():
        task.cancel()
        return {"ok": True, "cancelled": True}
    return {"ok": True, "cancelled": False}
