"""Network tools — port check."""

from __future__ import annotations

import socket

from pydantic import BaseModel, Field

from agentica.tools.base import BaseTool, BaseTarget, RiskTier, ToolCategory, ToolSpec
from agentica.tools.registry import registry


class CheckPortInput(BaseModel):
    host: str = Field(..., description="Host to check")
    port: int = Field(..., ge=1, le=65535, description="Port number")
    timeout: float = Field(default=3.0, description="Timeout in seconds")
    model_config = {"extra": "forbid"}


class CheckPortResult(BaseModel):
    host: str
    port: int
    open: bool
    model_config = {"extra": "forbid"}


class CheckPort(BaseTool[CheckPortInput, CheckPortResult]):
    spec = ToolSpec(
        name="check_port",
        description="Check if a TCP port is open on a host.",
        category=ToolCategory.NETWORK,
        risk_tier=RiskTier.READ,
        input_schema=CheckPortInput.model_json_schema(),
    )

    async def run(self, args: CheckPortInput, target: BaseTarget | None = None) -> CheckPortResult:
        try:
            with socket.create_connection((args.host, args.port), timeout=args.timeout):
                open_ = True
        except OSError:
            open_ = False
        return CheckPortResult(host=args.host, port=args.port, open=open_)


registry.register(CheckPort())
