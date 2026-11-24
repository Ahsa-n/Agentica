"""SSH target — Paramiko-based with host key pinning and 256 KB output cap."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import shlex
from concurrent.futures import ThreadPoolExecutor

import paramiko

from agentica.config.logging import get_logger
from agentica.tools.base import BaseTarget

logger = get_logger(__name__)

MAX_OUTPUT = 256 * 1024  # 256 KB
_POOL = ThreadPoolExecutor(max_workers=4)

# Key types tried in order when loading a private key from the keyring.
_KEY_CLASSES = (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey)


def fingerprints(key: paramiko.PKey) -> dict[str, str]:
    """Return the host key's MD5 (aa:bb:..) and SHA256 (SHA256:base64) fingerprints."""
    raw = key.asbytes()
    md5 = hashlib.md5(raw).hexdigest()
    sha256 = base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
    return {
        "md5": ":".join(md5[i:i + 2] for i in range(0, len(md5), 2)),
        "sha256": f"SHA256:{sha256}",
        "key_type": key.get_name(),
    }


def fingerprint_matches(key: paramiko.PKey, expected: str) -> bool:
    """Accept either the OpenSSH SHA256 form or the legacy MD5 hex form."""
    fps = fingerprints(key)
    exp = expected.strip()
    if exp.upper().startswith("SHA256:"):
        return exp.split(":", 1)[1].rstrip("=") == fps["sha256"].split(":", 1)[1]
    norm = exp.lower().replace(":", "")
    if norm.startswith("md5"):
        norm = norm[3:]
    return norm == fps["md5"].replace(":", "")


def fetch_host_fingerprint(host: str, port: int = 22, timeout: float = 10.0) -> dict[str, str]:
    """Connect without authenticating and report the server's host key fingerprint.

    Used by the Machines page so the administrator can compare it with the server
    (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`) before trusting it.
    """
    sock_transport = paramiko.Transport((host, port))
    try:
        sock_transport.banner_timeout = timeout
        sock_transport.start_client(timeout=timeout)
        return fingerprints(sock_transport.get_remote_server_key())
    finally:
        sock_transport.close()


def _load_private_key(text: str) -> paramiko.PKey:
    last_err: Exception | None = None
    for cls in _KEY_CLASSES:
        try:
            return cls.from_private_key(io.StringIO(text))
        except Exception as e:  # wrong type → try the next one
            last_err = e
    raise ValueError(f"Unsupported or invalid private key: {last_err}")


class SSHTarget(BaseTarget):
    os_family = "linux"

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
        if not self.trusted_fingerprint:
            raise paramiko.SSHException("Host key is not trusted; trust the machine first.")

        client = paramiko.SSHClient()
        # No known_hosts: every host key goes through the pinned-fingerprint policy,
        # which accepts only the key the administrator trusted.
        client.get_host_keys().clear()
        client.set_missing_host_key_policy(_PinnedKeyPolicy(self.trusted_fingerprint))

        connect_kwargs: dict = dict(
            hostname=self.host,
            port=self.port,
            username=self.username,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
            allow_agent=False,
            look_for_keys=False,
        )
        if self.private_key:
            connect_kwargs["pkey"] = _load_private_key(self.private_key)
        elif self.password:
            connect_kwargs["password"] = self.password

        client.connect(**connect_kwargs)
        return client

    def _run_sync(self, argv: list[str], timeout: int) -> tuple[int, str, str]:
        # SSH exec always goes through the remote user's shell, so every argv element
        # must be quoted; a plain " ".join would let a value like "nginx; rm -rf ~" run
        # as a second command. shlex.join gives argv semantics on a POSIX shell.
        cmd = shlex.join(a.decode() if isinstance(a, bytes) else str(a) for a in argv)

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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_POOL, self._run_sync, argv, timeout)


class _PinnedKeyPolicy(paramiko.MissingHostKeyPolicy):
    def __init__(self, expected: str) -> None:
        self._expected = expected

    def missing_host_key(self, client, hostname, key):
        if not fingerprint_matches(key, self._expected):
            fps = fingerprints(key)
            raise paramiko.SSHException(
                f"Host key fingerprint mismatch for {hostname}: expected {self._expected}, "
                f"got {fps['sha256']} ({fps['md5']}). The server key changed — refusing to connect."
            )
