"""Agent graph + registry wiring: validation, policy deny, target routing, turn reset."""

from __future__ import annotations

import pytest

from agentica.agent.graph import TURN_RESET, node_policy, node_validate
from agentica.agent.state import AgentState, RunConfig, ToolCall
from agentica.tools.base import FakeTarget
from agentica.tools.registry import registry


def _state(tc: ToolCall, **kw) -> AgentState:
    return AgentState(run_config=RunConfig(session_id="t"), pending_tool_call=tc, **kw)


@pytest.mark.asyncio
async def test_validate_accepts_valid_args_repeatedly():
    # Regression: validation used to raise on every call, so only the first tool call
    # of a turn survived. Two valid calls in a row must both pass.
    tc = ToolCall(call_id="1", tool_name="get_memory_usage", args={})
    out = await node_validate(_state(tc, validation_retries=1))
    assert out == {"validation_retries": 0}


@pytest.mark.asyncio
async def test_validate_rejects_extra_args():
    tc = ToolCall(call_id="1", tool_name="get_service_status", args={"name": "nginx", "evil": 1})
    out = await node_validate(_state(tc))
    assert "Invalid arguments" in out["pending_tool_call"].error


@pytest.mark.asyncio
async def test_validate_rejects_option_like_service_name():
    tc = ToolCall(call_id="1", tool_name="restart_service", args={"name": "--help"})
    out = await node_validate(_state(tc))
    assert out["pending_tool_call"].error


@pytest.mark.asyncio
async def test_validate_unknown_tool():
    tc = ToolCall(call_id="1", tool_name="format_disk", args={})
    out = await node_validate(_state(tc))
    assert "Unknown tool" in out["pending_tool_call"].error


@pytest.mark.asyncio
async def test_policy_deny_records_error_for_the_llm():
    tc = ToolCall(call_id="1", tool_name="restart_service", args={"name": "sshd"})
    out = await node_policy(_state(tc))
    assert out["pending_tool_call"].policy_decision == "deny"
    assert out["pending_tool_call"].error.startswith("Denied by policy")


def test_turn_reset_clears_per_turn_fields():
    for field in ("final_answer", "pending_tool_call", "step_count", "deny_count", "routed_categories"):
        assert field in TURN_RESET


def test_target_param_injected_only_for_remote_capable_tools():
    tools = {t["function"]["name"]: t for t in registry.to_langchain_tools(targets=["linux-1"])}
    cpu_props = tools["get_cpu_usage"]["function"]["parameters"]["properties"]
    assert cpu_props["target"]["enum"] == ["linux-1"]
    kb_props = tools["search_knowledge_base"]["function"]["parameters"].get("properties", {})
    assert "target" not in kb_props
    # The tool's own input model is not mutated
    assert "target" not in registry.get("get_cpu_usage").spec.input_schema.get("properties", {})


def test_no_target_param_without_registered_targets():
    tools = {t["function"]["name"]: t for t in registry.to_langchain_tools(targets=[])}
    assert "target" not in tools["get_cpu_usage"]["function"]["parameters"].get("properties", {})


class _ToolCallingLLM:
    def __init__(self, args):
        self._args = args

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        from langchain_core.messages import AIMessage
        return AIMessage(content="", tool_calls=[{"name": "get_cpu_usage", "args": dict(self._args), "id": "c1"}])


@pytest.mark.asyncio
@pytest.mark.parametrize("user_text,llm_target,expected", [
    ("What is the CPU usage on linux-1?", "linux-1", "linux-1"),   # named by the user → used
    ("What is the CPU usage?", "linux-1", None),                   # not named → runs locally
    ("cpu please", "local", None),
])
async def test_agent_only_targets_machines_the_user_named(monkeypatch, user_text, llm_target, expected):
    from langchain_core.messages import HumanMessage
    import agentica.agent.graph as graph_mod

    monkeypatch.setattr(graph_mod, "get_provider", lambda: _ToolCallingLLM({"target": llm_target}))
    monkeypatch.setattr("agentica.tools.remote.target_manager.list_target_ids", lambda: ["linux-1"])
    state = AgentState(run_config=RunConfig(session_id="t", routing_mode="flat"),
                       messages=[HumanMessage(content=user_text)])
    out = await graph_mod.node_agent(state)
    assert out["pending_tool_call"].target_id == expected
    assert "target" not in out["pending_tool_call"].args


@pytest.mark.asyncio
async def test_monitoring_tool_runs_on_remote_target():
    from agentica.tools.local.monitoring import EmptyInput
    from agentica.tools.remote.linux import CPU_SCRIPT, _SPLIT

    out = f"cpu 1 0 1 8 0\ncpu0 1 0 1 8 0\n{_SPLIT}\ncpu 2 0 2 16 0\ncpu0 2 0 2 16 0\n{_SPLIT}\n1.0 0.5 0.2 1/2 3\n"
    t = FakeTarget({f"sh -c {CPU_SCRIPT}": (0, out, "")})
    r = await registry.get("get_cpu_usage").run(EmptyInput(), target=t)
    assert r.core_count == 1 and r.load_avg == [1.0, 0.5, 0.2]
    assert t.calls  # ran on the target, not via psutil


@pytest.mark.asyncio
async def test_app_status_on_remote_target():
    from agentica.tools.local.apps import AppStatusInput

    t = FakeTarget({
        "ps -eo comm=": (0, "bash\nnginx\nsshd\n", ""),
        "cat /proc/net/tcp /proc/net/tcp6": (0, "  sl local rem st\n   0: 00000000:0050 00000000:0000 0A x\n", ""),
    })
    r = await registry.get("get_application_status").run(AppStatusInput(app_id="nginx"), target=t)
    assert r.apps[0].status == "UP"
    assert {c.check for c in r.apps[0].checks} == {"process", "port"}
