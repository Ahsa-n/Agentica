"""Kill-and-resume: the backend restarts while a run waits for approval; after
approval the tool executes exactly once.

Needs PostgreSQL (docker compose -f infra/docker-compose.dev.yml up -d postgres):
    CI_INTEGRATION=1 pytest tests/integration
The LLM is replaced by a deterministic fake so the test checks graph/checkpoint
semantics, not model behaviour.
"""

from __future__ import annotations

import os
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel

pytestmark = pytest.mark.skipif(
    os.getenv("CI_INTEGRATION") != "1",
    reason="Integration test: set CI_INTEGRATION=1 and have PostgreSQL running",
)

EXECUTIONS: list[str] = []


class _NoArgs(BaseModel):
    model_config = {"extra": "forbid"}


class _Done(BaseModel):
    ok: bool
    model_config = {"extra": "forbid"}


def _counter_tool():
    from agentica.tools.base import BaseTool, RiskTier, ToolCategory, ToolSpec

    class CountingModifyTool(BaseTool[_NoArgs, _Done]):
        spec = ToolSpec(
            name="test_counting_modify",
            description="Test-only modify tool that counts executions.",
            category=ToolCategory.SERVICES,
            risk_tier=RiskTier.MODIFY,  # -> policy default is Confirm
            input_schema=_NoArgs.model_json_schema(),
        )

        async def run(self, args, target=None):
            EXECUTIONS.append("run")
            return _Done(ok=True)

        async def verify(self, args, result, target=None):
            return True

    return CountingModifyTool()


class _FakeLLM:
    """First call: request the counting tool. After its result: final answer."""

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        if isinstance(messages[-1], ToolMessage):
            return AIMessage(content="Action completed.")
        return AIMessage(content="", tool_calls=[
            {"name": "test_counting_modify", "args": {}, "id": f"call-{uuid.uuid4()}"}
        ])


@pytest.fixture
def patched(monkeypatch):
    import agentica.agent.graph as graph_mod
    from agentica.tools.registry import registry

    tool = _counter_tool()
    registry.register(tool)
    monkeypatch.setattr(graph_mod, "get_provider", lambda: _FakeLLM())
    EXECUTIONS.clear()
    yield graph_mod
    registry._tools.pop(tool.spec.name, None)


def _dsn() -> str:
    from agentica.db.engine import get_dsn
    return get_dsn(async_=True).replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.mark.asyncio
async def test_kill_and_resume_executes_exactly_once(patched):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.types import Command
    from agentica.agent.state import RunConfig

    graph_mod = patched
    session_id = f"kill-resume-{uuid.uuid4()}"
    config = graph_mod.run_config_for(session_id)
    state_input = {
        **graph_mod.TURN_RESET,
        "messages": [HumanMessage(content="do the counted action")],
        "run_config": RunConfig(session_id=session_id, routing_mode="flat"),
    }

    # ── Process 1: run until the approval interrupt, then "die" ────────────
    async with AsyncPostgresSaver.from_conn_string(_dsn()) as cp1:
        await cp1.setup()
        graph1 = graph_mod.build_graph(checkpointer=cp1)
        async for _ in graph1.astream(state_input, config=config, stream_mode="values"):
            pass
        snap = await graph1.aget_state(config)
        assert snap.next == ("approval",), f"expected to wait at approval, got {snap.next}"
        assert snap.values["pending_tool_call"].policy_decision == "confirm"
        assert EXECUTIONS == [], "tool must not run before approval"
    # connection closed: nothing of process 1 survives except the checkpoint

    # ── Process 2: fresh connection + graph, approve, resume ───────────────
    async with AsyncPostgresSaver.from_conn_string(_dsn()) as cp2:
        graph2 = graph_mod.build_graph(checkpointer=cp2)
        snap = await graph2.aget_state(config)
        assert snap.next == ("approval",), "pending approval must survive the restart"

        result = await graph2.ainvoke(Command(resume={"approved": True}), config=config)
        assert EXECUTIONS == ["run"], f"tool executed {len(EXECUTIONS)} times, expected exactly 1"
        assert result["final_answer"] == "Action completed."

        after = await graph2.aget_state(config)
        assert after.next == (), "run must be finished after approval"
        history = after.values["tool_calls_history"]
        assert len(history) == 1 and history[0].result["verified"] is True


@pytest.mark.asyncio
async def test_denied_after_restart_never_executes(patched):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.types import Command
    from agentica.agent.state import RunConfig

    graph_mod = patched
    session_id = f"kill-deny-{uuid.uuid4()}"
    config = graph_mod.run_config_for(session_id)
    state_input = {
        **graph_mod.TURN_RESET,
        "messages": [HumanMessage(content="do the counted action")],
        "run_config": RunConfig(session_id=session_id, routing_mode="flat"),
    }
    async with AsyncPostgresSaver.from_conn_string(_dsn()) as cp1:
        await cp1.setup()
        async for _ in graph_mod.build_graph(checkpointer=cp1).astream(state_input, config=config, stream_mode="values"):
            pass

    async with AsyncPostgresSaver.from_conn_string(_dsn()) as cp2:
        graph2 = graph_mod.build_graph(checkpointer=cp2)
        await graph2.ainvoke(Command(resume={"approved": False}), config=config)
        assert EXECUTIONS == [], "a denied action must never execute"
        after = await graph2.aget_state(config)
        assert after.next == ()
