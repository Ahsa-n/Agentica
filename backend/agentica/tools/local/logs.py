"""Log retrieval tools — journald (Linux) / Event Log (Windows), local or remote."""

from __future__ import annotations

import json
import re
import sys

from pydantic import BaseModel, Field, field_validator

from agentica.tools.base import BaseTool, BaseTarget, LocalTarget, RiskTier, ToolCategory, ToolSpec
from agentica.tools.registry import registry
from agentica.tools.remote.collectors import backend_for, is_remote

# Unit / log names are validated, then passed as a single argv element (Linux) or a
# ps_quote()d literal (Windows) — never spliced into a shell command string.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._:/\- ]{0,127}$")


class GetLogsInput(BaseModel):
    source: str = Field(
        ...,
        description="Log source: 'journal:<unit>' for Linux systemd, 'eventlog:<LogName>' for Windows"
    )
    lines: int = Field(default=50, ge=1, le=1000, description="Number of recent lines to return")
    contains: str | None = Field(default=None, max_length=200,
                                 description="Only return lines containing this text (case-insensitive)")
    model_config = {"extra": "forbid"}

    @field_validator("source")
    @classmethod
    def _check_source(cls, v: str) -> str:
        kind, sep, name = v.partition(":")
        if not sep or kind not in ("journal", "eventlog"):
            raise ValueError("source must be 'journal:<unit>' or 'eventlog:<LogName>'")
        if not _NAME_RE.match(name):
            raise ValueError(f"invalid log name {name!r}")
        return v


class GetLogsResult(BaseModel):
    source: str
    lines: list[str]
    error: str | None = None
    model_config = {"extra": "forbid"}


def _filter(lines: list[str], contains: str | None, limit: int) -> list[str]:
    # Filtering happens here in Python, never in a remote/local shell pipeline.
    if contains:
        needle = contains.lower()
        lines = [ln for ln in lines if needle in ln.lower()]
    return lines[-limit:]


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
        kind, _, name = args.source.partition(":")
        try:
            if is_remote(target):
                be = backend_for(target)
                if (kind == "journal") != (target.os_family == "linux"):
                    return GetLogsResult(source=args.source, lines=[], error=(
                        f"'{kind}:' logs are not available on a {target.os_family} machine; use "
                        f"{'journal:<unit>' if target.os_family == 'linux' else 'eventlog:<LogName>'}"))
                raw = await be.logs(target, name, 1000 if args.contains else args.lines)
            elif kind == "journal":
                raw = await self._get_journal(name, 1000 if args.contains else args.lines)
            else:
                raw = await self._get_eventlog(name, 1000 if args.contains else args.lines)
        except Exception as e:
            return GetLogsResult(source=args.source, lines=[], error=str(e)[:300])
        return GetLogsResult(source=args.source, lines=_filter(raw, args.contains, args.lines))

    async def _get_journal(self, unit: str, lines: int) -> list[str]:
        if sys.platform == "win32":
            raise RuntimeError("journald is not available on Windows; use 'eventlog:<LogName>'")
        rc, out, err = await LocalTarget().run_command(
            ["journalctl", "-u", unit, "--no-pager", "-n", str(lines), "--output=short"],
            timeout=15,
        )
        if rc != 0:
            raise RuntimeError(err.strip() or f"journalctl exited {rc}")
        return out.splitlines()

    async def _get_eventlog(self, log_name: str, lines: int) -> list[str]:
        if sys.platform != "win32":
            raise RuntimeError("Windows Event Log is only available on Windows; use 'journal:<unit>'")
        from agentica.tools.remote.winrm_target import ps_quote
        ps_cmd = (
            f"@(Get-WinEvent -LogName {ps_quote(log_name)} -MaxEvents {int(lines)} | Select-Object "
            "@{n='Time';e={$_.TimeCreated.ToString('s')}},LevelDisplayName,ProviderName,Message) "
            "| ConvertTo-Json -Compress -Depth 2"
        )
        rc, out, err = await LocalTarget().run_command(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            timeout=30,
        )
        if rc != 0:
            raise RuntimeError(err.strip()[:300] or f"powershell exited {rc}")
        entries = json.loads(out) if out.strip() else []
        if isinstance(entries, dict):
            entries = [entries]
        return [
            f"{e.get('Time', '')} [{e.get('LevelDisplayName', '')}] {e.get('ProviderName', '')}: "
            f"{str(e.get('Message') or '')[:200]}"
            for e in entries
        ]


registry.register(GetLogs())
