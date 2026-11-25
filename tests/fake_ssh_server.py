"""
A tiny real SSH server (paramiko) for testing Agentica's Linux support on Windows.

It accepts one username/password, takes the exact command Agentica sends (`python3 -c '<bootstrap>'`),
runs it with this PC's Python and AGENTICA_TEST_ROOT pointing at tests/fixtures/linux (recorded Linux
data), and streams stdout / stderr / exit code back over the SSH channel.

    python tests/fake_ssh_server.py --host 127.0.0.2 --port 2222 --user agentica --password secret
"""
import argparse
import os
import shlex
import socket
import subprocess
import sys
import threading
from pathlib import Path

import paramiko

FIXTURE = str(Path(__file__).resolve().parent / "fixtures" / "linux").replace("\\", "/")


class Server(paramiko.ServerInterface):
    def __init__(self, user, password):
        self.user, self.password = user, password
        self.exec_event = threading.Event()
        self.command = None

    def check_auth_password(self, username, password):
        ok = username == self.user and password == self.password
        return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        self.command = command.decode()
        threading.Thread(target=self._exec, args=(channel, self.command), daemon=True).start()
        return True

    def _exec(self, channel, command):
        argv = shlex.split(command)
        if argv and argv[0] == "python3":
            argv[0] = sys.executable
        data = b""
        while True:                                   # Agentica writes the payload, then closes its side
            chunk = channel.recv(65536)
            if not chunk:
                break
            data += chunk
        try:
            r = subprocess.run(argv, input=data, capture_output=True, timeout=60,
                               env={**os.environ, "AGENTICA_TEST_ROOT": FIXTURE})
            channel.sendall(r.stdout)
            channel.sendall_stderr(r.stderr)
            channel.send_exit_status(r.returncode)
        except FileNotFoundError:
            channel.sendall_stderr(f"sh: 1: {argv[0]}: not found\n".encode())
            channel.send_exit_status(127)
        finally:
            channel.close()


def serve(host, port, user, password):
    key = paramiko.RSAKey.generate(2048)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(20)
    print(f"fake SSH server on {host}:{port} (user {user})", flush=True)
    while True:
        client, _ = sock.accept()
        threading.Thread(target=_session, args=(client, key, user, password), daemon=True).start()


def _session(client, key, user, password):
    t = paramiko.Transport(client)
    t.add_server_key(key)
    try:
        t.start_server(server=Server(user, password))
        while t.is_active():
            ch = t.accept(timeout=60)
            if ch is None:
                continue
    except Exception:  # noqa: BLE001 - a dropped test connection is fine
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.2")
    ap.add_argument("--port", type=int, default=2222)
    ap.add_argument("--user", default="agentica")
    ap.add_argument("--password", default="secret")
    a = ap.parse_args()
    serve(a.host, a.port, a.user, a.password)
