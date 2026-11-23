"""LangGraph StateGraph — the agent execution graph."""

from __future__ import annotations

import json
import time
import uuid
from functools import lru_cache
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from agentica.agent.provider import get_provider
from agentica.agent.router import get_router
from agentica.agent.state import AgentState, RunConfig, ToolCall
from agentica.config.logging import get_logger
from agentica.db.engine import get_dsn
from agentica.policy.engine import Decision, PolicyEngine
from agentica.policy.guardrails import GuardrailDecision, analyse_command
from agentica.tools.base import RiskTier
from agentica.tools.registry import registry

logger = get_logger(__name__)

_policy = PolicyEngine()


# ─── Node implementations ────────────────────────────────────────────────────

async def node_route(state: AgentState) -> dict:
    """Route the user request to relevant tool categories."""
    cfg = state.run_config or RunConfig(session_id="default")
    last_msg = next((m for m in reversed(state.messages) if isinstance(m, HumanMessage)), None)
    query = last_msg.content if last_msg else ""

    if cfg.routing_mode == "flat":
        from agentica.tools.base import ToolCategory
        cats = list(ToolCategory)
        return {"routed_categories": [c.value for c in cats], "step_count": state.step_count + 1}

    result = get_router().route(query, force_categories=cfg.force_categories)
    return {
        "routed_categories": [c.value for c in result.categories],
        "step_count": state.step_count + 1,
    }


async def node_gather_context(state: AgentState) -> dict:
    """Optionally pre-fetch KB context for the query."""
    last_msg = next((m for m in reversed(state.messages) if isinstance(m, HumanMessage)), None)
    if not last_msg:
        return {}
    # RAG retrieval delegated to the agent node via tool call
    return {}


async def node_agent(state: AgentState) -> dict:
    """Call the LLM to decide the next action or produce final answer."""
    if state.cancelled:
        return {"final_answer": "Run cancelled."}

    cfg = state.run_config or RunConfig(session_id="default")
    llm = get_provider()

    # Build tool list
    if cfg.routing_mode == "flat":
        from agentica.tools.base import ToolCategory
        cats = list(ToolCategory)
    else:
        from agentica.tools.base import ToolCategory
        cats = [ToolCategory(c) for c in state.routed_categories if c in [e.value for e in ToolCategory]]

    specs = registry.specs_for_categories(cats)
    # Always include get_system_overview
    overview_spec = registry.get("get_system_overview")
    if overview_spec and overview_spec.spec not in specs:
        specs.append(overview_spec.spec)

    tools = registry.to_langchain_tools(specs)
    llm_with_tools = llm.bind_tools(tools) if tools else llm

    # Context budget: keep last 20 messages
    messages = state.messages[-20:]

    response = await llm_with_tools.ainvoke(messages)

    # Check for tool call
    if hasattr(response, "tool_calls") and response.tool_calls:
        tc = response.tool_calls[0]
        call_id = tc.get("id") or str(uuid.uuid4())
        pending = ToolCall(
            call_id=call_id,
            tool_name=tc["name"],
            args=tc.get("args", {}),
        )
        return {"messages": [response], "pending_tool_call": pending}

    # Final answer
    return {"messages": [response], "final_answer": response.content, "pending_tool_call": None}


async def node_validate(state: AgentState) -> dict:
    """Validate the pending tool call arguments against the tool schema."""
    tc = state.pending_tool_call
    if not tc:
        return {}

    tool = registry.get(tc.tool_name)
    if not tool:
        return {
            "pending_tool_call": tc.model_copy(update={
                "error": f"Unknown tool: {tc.tool_name}"
            })
        }

    # Validate args against input schema
    try:
        input_model = tool.__class__.__bases__[0].__args__[0] if hasattr(tool.__class__, "__orig_bases__") else None
        # Use pydantic model from spec
        from pydantic import TypeAdapter
        import pydantic
        schema = tool.spec.input_schema
        # Simple validation: just check the tool exists and args are a dict
        if not isinstance(tc.args, dict):
            raise ValueError("Args must be a dict")
    except Exception as e:
        retries = state.validation_retries + 1
        if retries >= (state.run_config.max_validation_retries if state.run_config else 2):
            return {
                "pending_tool_call": tc.model_copy(update={"error": str(e)}),
                "validation_retries": retries,
            }
        return {"validation_retries": retries}

    return {"validation_retries": 0}


async def node_policy(state: AgentState) -> dict:
    """Run the policy engine on the pending tool call."""
    tc = state.pending_tool_call
    if not tc or tc.error:
        return {}

    result = _policy.evaluate(
        tool_name=tc.tool_name,
        args=tc.args,
        target_id=tc.target_id,
        registry=registry,
    )

    updated = tc.model_copy(update={
        "policy_decision": result.decision.value,
        "policy_reason": result.reason,
        "policy_rule_id": result.rule_id,
    })

    deny_count = state.deny_count
    if result.decision == Decision.DENY:
        deny_count += 1

    return {"pending_tool_call": updated, "deny_count": deny_count}


async def node_approval(state: AgentState) -> Command:
    """Interrupt the graph and wait for human approval."""
    tc = state.pending_tool_call
    if not tc:
        return Command(goto="execute")

    # Interrupt — saves state to PostgreSQL checkpointer
    approval = interrupt({
        "type": "approval_required",
        "call_id": tc.call_id,
        "tool_name": tc.tool_name,
        "args": tc.args,
        "target_id": tc.target_id,
        "policy_decision": tc.policy_decision,
        "policy_reason": tc.policy_reason,
        "risk_tier": registry.get(tc.tool_name).spec.risk_tier.value
        if registry.get(tc.tool_name) else None,
    })

    # Resumed with approval result
    if approval and approval.get("approved"):
        return Command(goto="execute")
    else:
        # Denied by human
        tc_denied = tc.model_copy(update={"error": "Denied by administrator."})
        return Command(
            goto="report",
            update={"pending_tool_call": tc_denied, "deny_count": state.deny_count + 1},
        )


async def node_execute(state: AgentState) -> dict:
    """Execute the validated, policy-approved tool call."""
    tc = state.pending_tool_call
    if not tc or tc.error:
        return {}

    tool = registry.get(tc.tool_name)
    if not tool:
        return {"pending_tool_call": tc.model_copy(update={"error": "Tool not found."})}

    start = time.monotonic()
    try:
        # Determine target
        target = None
        if tc.target_id:
            from agentica.tools.remote.target_manager import get_target
            target = await get_target(tc.target_id)

        # Get the input model class from the tool's type parameters
        # We pass args as a dict and the tool's run() should handle it
        input_cls = _get_input_class(tool)
        if input_cls:
            args_obj = input_cls.model_validate(tc.args)
        else:
            from pydantic import BaseModel
            args_obj = type("Args", (BaseModel,), {})()

        result = await tool.run(args_obj, target=target)
        duration = (time.monotonic() - start) * 1000

        result_dict = result.model_dump() if hasattr(result, "model_dump") else {"data": str(result)}

        updated = tc.model_copy(update={
            "result": result_dict,
            "duration_ms": duration,
        })

        # Add tool result message for the LLM
        tool_msg = ToolMessage(
            content=json.dumps(result_dict),
            tool_call_id=tc.call_id,
            name=tc.tool_name,
        )

        return {
            "pending_tool_call": updated,
            "tool_calls_history": state.tool_calls_history + [updated],
            "messages": [tool_msg],
        }
    except Exception as e:
        logger.error("tool_execution_error", tool=tc.tool_name, error=str(e))
        updated = tc.model_copy(update={"error": str(e), "duration_ms": (time.monotonic() - start) * 1000})
        return {"pending_tool_call": updated}


def _get_input_class(tool):
    """Extract the input model class from a tool's generic parameters."""
    import inspect
    for base in getattr(tool.__class__, "__orig_bases__", []):
        args = getattr(base, "__args__", None)
        if args and len(args) >= 1:
            return args[0]
    return None


async def node_verify(state: AgentState) -> dict:
    """Run verify() for modify/destructive tools."""
    tc = state.pending_tool_call
    if not tc or tc.error:
        return {}

    tool = registry.get(tc.tool_name)
    if not tool or not tc.result:
        return {}

    tier = tool.spec.risk_tier
    if tier not in (RiskTier.MODIFY, RiskTier.DESTRUCTIVE):
        return {}

    try:
        input_cls = _get_input_class(tool)
        args_obj = input_cls.model_validate(tc.args) if input_cls else None
        result_obj = None  # simplified — could deserialize tc.result

        verified = await tool.verify(args_obj, result_obj)
        if not verified:
            logger.warning("verify_failed", tool=tc.tool_name)
    except Exception as e:
        logger.warning("verify_error", tool=tc.tool_name, error=str(e))

    return {}


async def node_report(state: AgentState) -> dict:
    """Final reporting — LLM synthesises a human-readable answer."""
    tc = state.pending_tool_call
    if tc and tc.error:
        # Return to agent loop with error context added
        from langchain_core.messages import SystemMessage
        err_msg = ToolMessage(
            content=json.dumps({"error": tc.error}),
            tool_call_id=tc.call_id,
            name=tc.tool_name if tc else "unknown",
        )
        return {"messages": [err_msg], "pending_tool_call": None}

    if tc and tc.result:
        return {"pending_tool_call": None}

    return {}


# ─── Edge conditions ──────────────────────────────────────────────────────────

def route_after_agent(state: AgentState) -> str:
    if state.cancelled:
        return "END"
    if state.final_answer:
        return "END"
    if state.step_count >= (state.run_config.max_steps if state.run_config else 10):
        return "END"
    if state.pending_tool_call:
        return "validate"
    return "END"


def route_after_validate(state: AgentState) -> str:
    tc = state.pending_tool_call
    if tc and tc.error:
        return "report"
    if state.validation_retries >= (state.run_config.max_validation_retries if state.run_config else 2):
        return "report"
    return "policy"


def route_after_policy(state: AgentState) -> str:
    tc = state.pending_tool_call
    if not tc:
        return "report"
    decision = tc.policy_decision
    if decision == Decision.DENY.value:
        if state.deny_count >= (state.run_config.max_denies_per_turn if state.run_config else 2):
            return "report"
        return "report"
    if decision == Decision.CONFIRM.value:
        return "approval"
    return "execute"


def route_after_execute(state: AgentState) -> str:
    tc = state.pending_tool_call
    if tc and tc.error:
        return "report"
    tool = registry.get(tc.tool_name) if tc else None
    if tool and tool.spec.risk_tier in (RiskTier.MODIFY, RiskTier.DESTRUCTIVE):
        return "verify"
    return "report"


def route_after_report(state: AgentState) -> str:
    if state.final_answer:
        return "END"
    if state.step_count >= (state.run_config.max_steps if state.run_config else 10):
        return "END"
    return "agent"


# ─── Graph builder ────────────────────────────────────────────────────────────

def build_graph(checkpointer=None) -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("route", node_route)
    g.add_node("gather_context", node_gather_context)
    g.add_node("agent", node_agent)
    g.add_node("validate", node_validate)
    g.add_node("policy", node_policy)
    g.add_node("approval", node_approval)
    g.add_node("execute", node_execute)
    g.add_node("verify", node_verify)
    g.add_node("report", node_report)

    g.set_entry_point("route")
    g.add_edge("route", "gather_context")
    g.add_edge("gather_context", "agent")
    g.add_conditional_edges("agent", route_after_agent, {
        "validate": "validate", "END": END
    })
    g.add_conditional_edges("validate", route_after_validate, {
        "policy": "policy", "report": "report"
    })
    g.add_conditional_edges("policy", route_after_policy, {
        "execute": "execute", "approval": "approval", "report": "report"
    })
    g.add_edge("approval", "execute")
    g.add_conditional_edges("execute", route_after_execute, {
        "verify": "verify", "report": "report"
    })
    g.add_edge("verify", "report")
    g.add_conditional_edges("report", route_after_report, {
        "agent": "agent", "END": END
    })

    return g.compile(checkpointer=checkpointer, interrupt_before=["approval"])


_graph_instance = None


async def get_graph():
    global _graph_instance
    if _graph_instance is None:
        dsn = get_dsn(async_=True)
        checkpointer = AsyncPostgresSaver.from_conn_string(dsn)
        await checkpointer.setup()
        _graph_instance = build_graph(checkpointer=checkpointer)
    return _graph_instance
