"""Tool framework — BaseTool, ToolRegistry, shared models."""

from __future__ import annotations

import abc
import json
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel


class RiskTier(str, Enum):
    READ = "read"
    MODIFY = "modify"
    DESTRUCTIVE = "destructive"


class ToolCategory(str, Enum):
    MONITORING = "monitoring"
    SERVICES = "services"
    APPLICATIONS = "applications"
    LOGS = "logs"
    NETWORK = "network"
    KNOWLEDGE = "knowledge"
    REMOTE = "remote"


class ToolError(BaseModel):
    tool: str
    error: str
    recoverable: bool = True

    model_config = {"extra": "forbid"}


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] = {}
    error: ToolError | None = None

    model_config = {"extra": "forbid"}


InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class ToolSpec(BaseModel):
    """Metadata for one tool, exported as a JSON schema for the LLM."""
    name: str
    description: str
    category: ToolCategory
    risk_tier: RiskTier
    input_schema: dict[str, Any]

    def to_langchain_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class ToolRegistry:
    """Central registry for all tools."""

    def __init__(self) -> None:
        self._tools: dict[str, "BaseTool"] = {}

    def register(self, tool: "BaseTool") -> None:
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> "BaseTool | None":
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def all_specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def specs_for_categories(self, categories: list[ToolCategory]) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values() if t.spec.category in categories]

    def to_langchain_tools(self, specs: list[ToolSpec] | None = None) -> list[dict]:
        target = specs or self.all_specs()
        names = {s.name for s in target}
        return [t.spec.to_langchain_tool() for t in self._tools.values() if t.spec.name in names]


class BaseTool(abc.ABC, Generic[InputT, OutputT]):
    """Abstract base class for all Agentica tools."""

    spec: ClassVar[ToolSpec]

    @abc.abstractmethod
    async def run(self, args: InputT, target: "BaseTarget | None" = None) -> OutputT:
        """Execute the tool and return structured output. Never raises."""

    async def verify(self, args: InputT, result: OutputT, target: "BaseTarget | None" = None) -> bool:
        """Optional post-execution verification for modify/destructive tools."""
        return True

    def _error_result(self, msg: str) -> ToolResult:
        return ToolResult(
            success=False,
            error=ToolError(tool=self.spec.name, error=msg),
        )


class BaseTarget(abc.ABC):
    """Abstract remote/local execution target."""

    @abc.abstractmethod
    async def run_command(self, argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
        """Run argv, return (returncode, stdout, stderr). Never uses shell=True."""


class LocalTarget(BaseTarget):
    """Execute commands on the local machine — argv only, no shell."""

    MAX_OUTPUT_BYTES = 256 * 1024  # 256 KB

    async def run_command(self, argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return 1, "", f"Command timed out after {timeout}s"

        stdout = stdout_b[: self.MAX_OUTPUT_BYTES].decode(errors="replace")
        stderr = stderr_b[: self.MAX_OUTPUT_BYTES].decode(errors="replace")
        return proc.returncode or 0, stdout, stderr


class FakeTarget(BaseTarget):
    """Deterministic fake target for unit tests."""

    def __init__(self, responses: dict[str, tuple[int, str, str]] | None = None) -> None:
        self._responses = responses or {}
        self.calls: list[list[str]] = []

    async def run_command(self, argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
        self.calls.append(argv)
        key = " ".join(argv)
        return self._responses.get(key, (0, "", ""))
