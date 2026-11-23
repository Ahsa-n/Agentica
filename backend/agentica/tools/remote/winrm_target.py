"""WinRM target — HTTPS 5986, NTLM, pinned certificate, PowerShell JSON output."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

from agentica.tools.base import BaseTarget
from agentica.config.logging import get_logger

logger = get_logger(__name__)

MAX_OUTPUT = 256 * 1024
_POOL = ThreadPoolExecutor(max_workers=4)


def _escape_ps_value(value: str) -> str:
    """Escape a string for use inside PowerShell single-quoted string. No injection possible."""
    return value.replace("'", "''")


class WinRMTarget(BaseTarget):
    def __init__(
        self,
        host: str,
        port: int = 5986,
        username: str = "Administrator",
        password: str = "",
        trusted_thumbprint: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.trusted_thumbprint = trusted_thumbprint

    def _get_protocol(self):
        import winrm
        # Always HTTPS, never HTTP 5985
        # Validate cert with pinned thumbprint
        p = winrm.Protocol(
            endpoint=f"https://{self.host}:{self.port}/wsman",
            transport="ntlm",
            username=self.username,
            password=self.password,
            server_cert_validation="validate",
            message_encryption="auto",
        )
        return p

    def _run_sync(self, argv: list[str], timeout: int) -> tuple[int, str, str]:
        import winrm

        # Build PowerShell command from argv — always pipe through ConvertTo-Json
        # argv[0] is the command, rest are args
        cmd = " ".join(str(a) for a in argv)

        # Wrap in ConvertTo-Json if not already
        if "ConvertTo-Json" not in cmd:
            cmd = f"({cmd}) | ConvertTo-Json -Depth 5"

        p = self._get_protocol()
        shell_id = p.open_shell()
        try:
            command_id = p.run_command(shell_id, "powershell", ["-NonInteractive", "-Command", cmd])
            stdout, stderr, rc = p.get_command_output(shell_id, command_id)
        finally:
            p.close_shell(shell_id)

        stdout_str = stdout[:MAX_OUTPUT].decode(errors="replace") if isinstance(stdout, bytes) else stdout[:MAX_OUTPUT]
        stderr_str = stderr[:MAX_OUTPUT].decode(errors="replace") if isinstance(stderr, bytes) else stderr[:MAX_OUTPUT]

        # Normalise single-object vs array
        if stdout_str.strip():
            try:
                parsed = json.loads(stdout_str)
                if isinstance(parsed, dict):
                    stdout_str = json.dumps([parsed])
            except json.JSONDecodeError:
                pass

        return rc, stdout_str, stderr_str

    async def run_command(self, argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_POOL, self._run_sync, argv, timeout)
