"""WinRM target — HTTPS 5986, NTLM, pinned certificate, PowerShell JSON output."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import ssl
import warnings
from concurrent.futures import ThreadPoolExecutor

from agentica.tools.base import BaseTarget
from agentica.config.logging import get_logger

logger = get_logger(__name__)

MAX_OUTPUT = 256 * 1024
_POOL = ThreadPoolExecutor(max_workers=4)

# PowerShell treats these Unicode quotes exactly like an ASCII single quote.
_PS_SINGLE_QUOTES = ("'", "‘", "’", "‚", "‛")


def ps_quote(value: str) -> str:
    """Return value as a PowerShell single-quoted literal.

    Inside '...' PowerShell expands nothing ($, backtick and $() are literal); the
    only special characters are the single-quote family, which are escaped by
    doubling. This is the escaping helper every model-supplied value goes through.
    """
    s = str(value)
    for q in _PS_SINGLE_QUOTES:
        s = s.replace(q, q + q)
    return f"'{s}'"


# Backwards-compatible name used by older code/tests.
def _escape_ps_value(value: str) -> str:
    return ps_quote(value)[1:-1]


def fetch_cert_thumbprint(host: str, port: int = 5986, timeout: float = 10.0) -> dict[str, str]:
    """Read the server's TLS certificate (no trust decision) and return its thumbprints.

    The administrator compares the SHA-1 thumbprint with the one printed by
    infra/windows-target-setup.ps1 before trusting the machine.
    """
    pem = ssl.get_server_certificate((host, port), timeout=timeout)
    der = ssl.PEM_cert_to_DER_cert(pem)
    return {
        "sha1": hashlib.sha1(der).hexdigest().upper(),
        "sha256": hashlib.sha256(der).hexdigest().upper(),
    }


def _normalise_thumbprint(tp: str) -> str:
    return tp.replace(":", "").replace(" ", "").lower()


class WinRMTarget(BaseTarget):
    os_family = "windows"

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
        from requests.adapters import HTTPAdapter

        if not self.trusted_thumbprint:
            raise RuntimeError("Certificate is not trusted; trust the machine first.")

        # Always HTTPS 5986 — never HTTP 5985.
        p = winrm.Protocol(
            endpoint=f"https://{self.host}:{self.port}/wsman",
            transport="ntlm",
            username=self.username,
            password=self.password,
            server_cert_validation="validate",
            message_encryption="auto",
        )

        # Certificate pinning. The target uses a self-signed certificate (created by
        # windows-target-setup.ps1), so CA-chain validation cannot succeed. Instead the
        # TLS layer must present exactly the certificate whose thumbprint the
        # administrator trusted (urllib3 assert_fingerprint); any other certificate
        # aborts the handshake. This is stricter than CA validation, not weaker.
        fingerprint = _normalise_thumbprint(self.trusted_thumbprint)

        class _PinnedAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                kwargs["assert_fingerprint"] = fingerprint
                return super().init_poolmanager(*args, **kwargs)

        transport = p.transport
        original_build = transport.build_session

        def pinned_build_session():
            session = original_build()
            session.verify = False  # chain check replaced by the fingerprint pin above
            session.mount("https://", _PinnedAdapter())
            return session

        transport.build_session = pinned_build_session
        return p

    def _run_ps_sync(self, script: str, timeout: int) -> tuple[int, str, str]:
        # -EncodedCommand (UTF-16LE base64) passes the script verbatim — no command-line
        # quoting layer exists for a value to escape from.
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Unverified HTTPS request")
            p = self._get_protocol()
            shell_id = p.open_shell()
            try:
                command_id = p.run_command(
                    shell_id, "powershell",
                    ["-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                )
                stdout, stderr, rc = p.get_command_output(shell_id, command_id)
            finally:
                p.close_shell(shell_id)

        out = stdout[:MAX_OUTPUT].decode("utf-8", errors="replace") if isinstance(stdout, bytes) else str(stdout)[:MAX_OUTPUT]
        err = stderr[:MAX_OUTPUT].decode("utf-8", errors="replace") if isinstance(stderr, bytes) else str(stderr)[:MAX_OUTPUT]
        if err.startswith("#< CLIXML"):
            err = _strip_clixml(err)
        return rc, out, err

    async def run_ps(self, script: str, timeout: int = 30) -> tuple[int, str, str]:
        """Run a PowerShell script built from constants + ps_quote()d values."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_POOL, self._run_ps_sync, script, timeout)

    async def run_command(self, argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
        """Run argv[0] with each further argv element passed as a quoted literal."""
        if not argv:
            return 1, "", "empty command"
        cmd = argv[0] if argv[0].replace("-", "").isalnum() else ps_quote(argv[0])
        script = "& " + " ".join([cmd, *(ps_quote(a) for a in argv[1:])])
        script = f"({script}) | ConvertTo-Json -Depth 5 -Compress"
        rc, out, err = await self.run_ps(script, timeout=timeout)
        # Normalise single-object vs array
        if out.strip():
            try:
                parsed = json.loads(out)
                if isinstance(parsed, dict):
                    out = json.dumps([parsed])
            except json.JSONDecodeError:
                pass
        return rc, out, err


def _strip_clixml(text: str) -> str:
    """PowerShell remoting returns stderr as CLIXML; pull out the readable lines."""
    import re
    lines = re.findall(r'<S S="Error">(.*?)</S>', text)
    msg = "".join(lines).replace("_x000D__x000A_", "\n").strip()
    return msg or text
