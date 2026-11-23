"""LangGraph agent state."""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    session_id: str
    routing_mode: str = "routed"
    max_steps: int = 10
    max_validation_retries: int = 2
    max_denies_per_turn: int = 2
    force_categories: list[str] = Field(default_factory=list)
    model_config = {"extra": "ignore"}


class ToolCall(BaseModel):
    call_id: str
    tool_name: str
    args: dict[str, Any]
    target_id: str | None = None
    policy_decision: str | None = None
    policy_reason: str | None = None
    policy_rule_id: str | None = None
    result: Any = None
    error: str | None = None
    duration_ms: float | None = None
    model_config = {"extra": "ignore"}


class AgentState(BaseModel):
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)
    run_config: RunConfig | None = None
    step_count: int = 0
    deny_count: int = 0
    validation_retries: int = 0
    routed_categories: list[str] = Field(default_factory=list)
    pending_tool_call: ToolCall | None = None
    tool_calls_history: list[ToolCall] = Field(default_factory=list)
    retrieved_chunks: list[dict] = Field(default_factory=list)
    final_answer: str | None = None
    error: str | None = None
    cancelled: bool = False
    model_config = {"extra": "ignore"}
