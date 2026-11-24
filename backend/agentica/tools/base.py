"""Tool framework — BaseTool, ToolRegistry, shared models."""

from __future__ import annotations

import abc
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


def _compact_schema(schema: Any) -> Any:
    """Deep copy of a JSON schema without Pydantic's redundant 'title' keys."""
    if isinstance(schema, dict):
        return {
            k: _compact_schema(v) for k, v in schema.items()
            # drop the "title" annotation, but keep a property literally named "title"
            if not (k == "title" and isinstance(v, str))
        }
    if isinstance(schema, list):
        return [_compact_schema(v) for v in schema]
    return schema


REMOTE_CAPABLE_CATEGORIES = frozenset({
    ToolCategory.MONITORING, ToolCategory.SERVICES, ToolCategory.APPLICATIONS,
    ToolCategory.LOGS, ToolCategory.NETWORK,
})


class ToolSpec(BaseModel):
    """Metadata for one tool, exported as a JSON schema for the LLM."""
    name: str
    description: str
    category: ToolCategory
    risk_tier: RiskTier
    input_schema: dict[str, Any]

    @property
    def remote_capable(self) -> bool:
        return self.category in REMOTE_CAPABLE_CATEGORIES

    def to_langchain_tool(self, targets: list[str] | None = None) -> dict[str, Any]:
        # Every token of tool schema is re-read by the model on every call; on a
        # CPU-only host that costs seconds. Pydantic's auto "title" fields add nothing.
        params = _compact_schema(self.input_schema)
        if targets and self.remote_capable:
            # `target` picks the machine; node_agent strips it from the args before
            # validation, so the tool's own input model never sees it.
            params.setdefault("properties", {})["target"] = {
                "type": "string",
                "enum": list(targets),
                "description": "Id of a registered remote machine to run on. Omit to run on the local machine.",
            }
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }


class ToolRegistry:
    """Central registry for all tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def all_specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def specs_for_categories(self, categories: list[ToolCategory]) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values() if t.spec.category in categories]

    def to_langchain_tools(self, specs: list[ToolSpec] | None = None, targets: list[str] | None = None) -> list[dict]:
        selected = specs or self.all_specs()
        names = {s.name for s in selected}
        return [t.spec.to_langchain_tool(targets) for t in self._tools.values() if t.spec.name in names]


class BaseTool(abc.ABC, Generic[InputT, OutputT]):
    """Abstract base class for all Agentica tools."""

    spec: ClassVar[ToolSpec]

    @abc.abstractmethod
    async def run(self, args: InputT, target: BaseTarget | None = None) -> OutputT:
        """Execute the tool and return structured output. Never raises."""

    async def verify(self, args: InputT, result: OutputT, target: BaseTarget | None = None) -> bool:
        """Optional post-execution verification for modify/destructive tools."""
        return True

    def _error_result(self, msg: str) -> ToolResult:
        return ToolResult(
            success=False,
            error=ToolError(tool=self.spec.name, error=msg),
        )


class BaseTarget(abc.ABC):
    """Abstract remote/local execution target.

    os_family selects the collector used by remote-capable tools:
    "local" (psutil on this machine), "linux" (SSH), "windows" (WinRM).
    """

    os_family: str = "local"

    @abc.abstractmethod
    async def run_command(self, argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
        """Run argv, return (returncode, stdout, stderr). Never uses shell=True."""


class LocalTarget(BaseTarget):
    """Execute commands on the local machine — argv only, no shell."""

    MAX_OUTPUT_BYTES = 256 * 1024  # 256 KB

    async def run_command(self, argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
        # subprocess.run in a worker thread instead of asyncio.create_subprocess_exec:
        # on Windows the backend must use the SelectorEventLoop (psycopg3 async), and
        # that loop cannot spawn subprocesses (NotImplementedError). argv list, no shell.
        import asyncio
        import subprocess
        import sys

        def _run() -> tuple[int, str, str]:
            try:
                proc = subprocess.run(
                    argv,
                    capture_output=True,
                    timeout=timeout,
                    shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
                )
            except subprocess.TimeoutExpired:
                return 1, "", f"Command timed out after {timeout}s"
            except FileNotFoundError:
                return 127, "", f"Command not found: {argv[0]}"
            stdout = proc.stdout[: self.MAX_OUTPUT_BYTES].decode(errors="replace")
            stderr = proc.stderr[: self.MAX_OUTPUT_BYTES].decode(errors="replace")
            return proc.returncode, stdout, stderr

        return await asyncio.to_thread(_run)


class FakeTarget(BaseTarget):
    """Deterministic fake target for unit tests."""

    def __init__(
        self,
        responses: dict[str, tuple[int, str, str]] | None = None,
        os_family: str = "linux",
        username: str = "root",
    ) -> None:
        self._responses = responses or {}
        self.calls: list[list[str]] = []
        self.os_family = os_family
        self.username = username
        self.host = "fake-host"

    async def run_ps(self, script: str, timeout: int = 30) -> tuple[int, str, str]:
        """Windows-style entry point: responses are keyed by the full script."""
        self.calls.append(["<ps>", script])
        return self._responses.get(script, (0, "", ""))

    async def run_command(self, argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
        self.calls.append(argv)
        key = " ".join(argv)
        return self._responses.get(key, (0, "", ""))
