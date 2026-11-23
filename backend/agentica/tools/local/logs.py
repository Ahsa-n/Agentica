"""Log retrieval tools."""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel, Field

from agentica.tools.base import BaseTool, BaseTarget, LocalTarget, RiskTier, ToolCategory, ToolSpec
from agentica.tools.registry import registry


class GetLogsInput(BaseModel):
    source: str = Field(
        ...,
        description="Log source: 'journal:<unit>' for Linux systemd, 'eventlog:<LogName>' for Windows"
    )
    lines: int = Field(default=50, ge=1, le=1000, description="Number of recent lines to return")
    model_config = {"extra": "forbid"}


class GetLogsResult(BaseModel):
    source: str
    lines: list[str]
    model_config = {"extra": "forbid"}


class GetLogs(BaseTool[GetLogsInput, GetLogsResult]):
    spec = ToolSpec(
        name="get_logs",
        description=(
            "Retrieve recent log entries. "
            "Use 'journal:<unit>' for Linux systemd journal (e.g. 'journal:nginx'), "
            "or 'eventlog:<LogName>' for Windows Event Log (e.g. 'eventlog:System')."
        ),
        category=ToolCategory.LOGS,
        risk_tier=RiskTier.READ,
        input_schema=GetLogsInput.model_json_schema(),
    )

    async def run(self, args: GetLogsInput, target: BaseTarget | None = None) -> GetLogsResult:
        src = args.source
        if src.startswith("journal:"):
            return await self._get_journal(src[len("journal:"):], args.lines)
        elif src.startswith("eventlog:"):
            return await self._get_eventlog(src[len("eventlog:"):], args.lines)
        else:
            return GetLogsResult(
                source=src,
                lines=[f"Unknown log source format: {src!r}. Use 'journal:<unit>' or 'eventlog:<LogName>'."],
            )

    async def _get_journal(self, unit: str, lines: int) -> GetLogsResult:
        # Filter in Python after bounded retrieval — never pass unit to shell
        rc, out, err = await LocalTarget().run_command(
            ["journalctl", "-u", unit, "--no-pager", f"-n{lines}", "--output=short"],
            timeout=15,
        )
        entries = out.splitlines() if rc == 0 else [f"Error: {err}"]
        return GetLogsResult(source=f"journal:{unit}", lines=entries[:lines])

    async def _get_eventlog(self, log_name: str, lines: int) -> GetLogsResult:
        # PowerShell with ConvertTo-Json, unit name validated
        safe_name = log_name.replace("'", "").replace('"', "").replace(";", "")
        ps_cmd = (
            f"Get-EventLog -LogName '{safe_name}' -Newest {lines} | "
            f"Select-Object TimeGenerated,EntryType,Source,Message | ConvertTo-Json -Depth 2"
        )
        rc, out, err = await LocalTarget().run_command(
            ["powershell", "-NonInteractive", "-Command", ps_cmd],
            timeout=20,
        )
        if rc != 0:
            return GetLogsResult(source=f"eventlog:{log_name}", lines=[f"Error: {err}"])
        import json
        try:
            entries = json.loads(out)
            if isinstance(entries, dict):
                entries = [entries]
            lines_out = [
                f"{e.get('TimeGenerated','')} [{e.get('EntryType','')}] {e.get('Source','')}: {e.get('Message','')[:200]}"
                for e in entries
            ]
        except Exception:
            lines_out = out.splitlines()[:lines]
        return GetLogsResult(source=f"eventlog:{log_name}", lines=lines_out)


registry.register(GetLogs())
