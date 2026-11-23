"""SSH target — Paramiko-based with host key pinning and 256 KB output cap."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import paramiko

from agentica.tools.base import BaseTarget
from agentica.config.logging import get_logger

logger = get_logger(__name__)

MAX_OUTPUT = 256 * 1024  # 256 KB
_POOL = ThreadPoolExecutor(max_workers=4)


class SSHTarget(BaseTarget):
    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "agentica",
        password: str | None = None,
        private_key: str | None = None,
        trusted_fingerprint: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.trusted_fingerprint = trusted_fingerprint

    def _connect(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()

        if self.trusted_fingerprint:
            client.get_host_keys().clear()
            # We'll verify fingerprint after connection
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())

        connect_kwargs = dict(
            hostname=self.host,
            port=self.port,
            username=self.username,
            timeout=10,
            allow_agent=False,
            look_for_keys=False,
        )
        if self.private_key:
            import io
            pkey = paramiko.RSAKey.from_private_key(io.StringIO(self.private_key))
            connect_kwargs["pkey"] = pkey
        elif self.password:
            connect_kwargs["password"] = self.password

        # Set up known hosts with pinned fingerprint
        if self.trusted_fingerprint:
            client.set_missing_host_key_policy(_PinnedKeyPolicy(self.trusted_fingerprint))

        client.connect(**connect_kwargs)
        return client

    def _run_sync(self, argv: list[str], timeout: int) -> tuple[int, str, str]:
        # Use sudo -n for privilege escalation (pre-configured in sudoers)
        cmd = " ".join(paramiko.common.asbytes(a).decode() if isinstance(a, bytes) else str(a) for a in argv)

        client = self._connect()
        try:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
            stdout_data = stdout.read(MAX_OUTPUT).decode(errors="replace")
            stderr_data = stderr.read(MAX_OUTPUT).decode(errors="replace")
            rc = stdout.channel.recv_exit_status()
        finally:
            client.close()
        return rc, stdout_data, stderr_data

    async def run_command(self, argv: list[str], timeout: int = 30) -> tuple[int, str, str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_POOL, self._run_sync, argv, timeout)


class _PinnedKeyPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, expected: str) -> None:
        self._expected = expected.lower().replace(":", "")

    def missing_host_key(self, client, hostname, key):
        import hashlib
        fp = hashlib.md5(key.asbytes()).hexdigest()
        fp_colon = ":".join(fp[i:i+2] for i in range(0, len(fp), 2))
        actual = fp.replace(":", "")
        if actual != self._expected.replace(":", ""):
            raise paramiko.SSHException(
                f"Host key fingerprint mismatch for {hostname}: "
                f"expected {self._expected}, got {fp_colon}"
            )
