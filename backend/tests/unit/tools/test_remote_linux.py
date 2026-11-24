"""Linux remote collectors: parser fixtures, argv safety, sudo, SysV fallback."""

from __future__ import annotations

import pytest

from agentica.tools.base import FakeTarget
from agentica.tools.remote import linux

PROC_STAT_A = """cpu  1000 0 500 8000 500 0 0 0 0 0
cpu0 500 0 250 4000 250 0 0 0 0 0
cpu1 500 0 250 4000 250 0 0 0 0 0
intr 12345
"""
PROC_STAT_B = """cpu  1300 0 600 8400 700 0 0 0 0 0
cpu0 700 0 300 4100 300 0 0 0 0 0
cpu1 600 0 300 4300 400 0 0 0 0 0
intr 12399
"""
CPU_OUT = f"{PROC_STAT_A}{linux._SPLIT}\n{PROC_STAT_B}{linux._SPLIT}\n0.52 0.41 0.30 1/123 4567\n"

MEMINFO = """MemTotal:        2048000 kB
MemFree:          256000 kB
MemAvailable:    1024000 kB
Buffers:           10000 kB
Cached:           300000 kB
SwapTotal:       1000000 kB
SwapFree:         750000 kB
"""

DF = """Filesystem     Type     1024-blocks     Used Available Capacity Mounted on
overlay        overlay     61255492 20411748  37701968      36% /
tmpfs          tmpfs          65536        0     65536       0% /dev
/dev/sdb1      ext4        10255636  9800000    455636      96% /var/lib/my data
"""

NET_DEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo:    1000      10    0    0    0     0          0         0     1000      10    0    0    0     0       0          0
  eth0: 5000000    4000    2    0    0     0          0         0  2500000    3000    1    0    0     0       0          0
"""

PS = """    1 root      0.0  0.1 Ss   bash
   42 www-data 12.5  3.2 S    nginx
   77 root     55.0  1.0 R    python3 worker
"""

PROC_NET_TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1 1
   1: 00000000:0050 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 2 1
   2: 0100007F:1F90 0100007F:D431 01 00000000:00000000 00:00000000 00000000     0        0 3 1
"""


def test_parse_cpu_two_samples():
    r = linux.parse_cpu(CPU_OUT)
    # busy = 1 - idle_delta/total_delta (idle = idle + iowait)
    # all:  total 11000-10000=1000, idle 9100-8500=600  -> 40%
    # cpu0: total  5400- 5000= 400, idle 4400-4250=150  -> 62.5%
    # cpu1: total  5600- 5000= 600, idle 4700-4250=450  -> 25%
    assert r.percent == 40.0
    assert r.core_count == 2
    assert r.per_cpu == [62.5, 25.0]
    assert r.load_avg == [0.52, 0.41, 0.30]


def test_parse_meminfo_uses_memavailable():
    r = linux.parse_meminfo(MEMINFO)
    assert r.total_gb == round(2048000 * 1024 / 1e9, 2)
    assert r.available_gb == round(1024000 * 1024 / 1e9, 2)
    assert r.percent == 50.0
    assert r.swap_used_gb == round(250000 * 1024 / 1e9, 2)


def test_parse_df_skips_pseudo_fs_and_keeps_spaces_in_mount():
    r = linux.parse_df(DF)
    mounts = [p.mountpoint for p in r.partitions]
    assert mounts == ["/", "/var/lib/my data"]
    assert r.partitions[1].percent == 96.0
    assert r.partitions[1].fstype == "ext4"


def test_parse_net_dev():
    r = linux.parse_net_dev(NET_DEV)
    eth0 = next(i for i in r.interfaces if i.name == "eth0")
    assert eth0.bytes_recv_mb == 5.0 and eth0.bytes_sent_mb == 2.5
    assert eth0.errin == 2 and eth0.errout == 1


def test_parse_ps_keeps_command_with_spaces():
    procs = linux.parse_ps(PS)
    assert [p.pid for p in procs] == [1, 42, 77]
    assert procs[2].name == "python3 worker" and procs[2].cpu_percent == 55.0


def test_parse_proc_net_tcp_listen_only():
    assert linux.parse_proc_net_tcp(PROC_NET_TCP) == [22, 80]


def test_parse_service_status_all():
    rows = linux.parse_service_status_all(" [ + ]  nginx\n [ - ]  cron\n [ ? ]  x11\n")
    assert rows == [("nginx", "active"), ("cron", "inactive"), ("x11", "unknown")]


@pytest.mark.asyncio
async def test_cpu_collector_uses_constant_script():
    t = FakeTarget({f"sh -c {linux.CPU_SCRIPT}": (0, CPU_OUT, "")})
    r = await linux.cpu(t)
    assert r.percent == 40.0
    assert t.calls == [["sh", "-c", linux.CPU_SCRIPT]]


@pytest.mark.asyncio
async def test_top_processes_sorted_and_limited():
    t = FakeTarget({"ps -eo pid=,user=,pcpu=,pmem=,stat=,comm=": (0, PS, "")})
    r = await linux.top_processes(t, limit=2, sort_by="cpu")
    assert [p.pid for p in r.processes] == [77, 42]
    r = await linux.top_processes(t, limit=1, sort_by="memory")
    assert r.processes[0].pid == 42


@pytest.mark.asyncio
async def test_service_status_systemd():
    out = "ActiveState=active\nLoadState=loaded\nDescription=A high performance web server\nMainPID=42\n"
    key = "systemctl show nginx --no-pager --property=ActiveState,LoadState,Description,MainPID"
    t = FakeTarget({key: (0, out, "")})
    assert await linux.service_status(t, "nginx") == ("active", "A high performance web server", 42)


@pytest.mark.asyncio
async def test_service_status_falls_back_to_sysv_without_systemd():
    key = "systemctl show nginx --no-pager --property=ActiveState,LoadState,Description,MainPID"
    t = FakeTarget({
        key: (1, "", "System has not been booted with systemd as init system (PID 1). Can't operate."),
        "service nginx status": (0, " * nginx is running\n", ""),
    })
    status, _, _ = await linux.service_status(t, "nginx")
    assert status == "active"
    assert t.calls[-1] == ["service", "nginx", "status"]


@pytest.mark.asyncio
async def test_service_action_uses_sudo_for_non_root():
    t = FakeTarget({"sudo -n systemctl restart nginx": (0, "", "")}, username="agentica")
    ok, msg = await linux.service_action(t, "nginx", "restart")
    assert ok and msg == "OK"
    assert t.calls == [["sudo", "-n", "systemctl", "restart", "nginx"]]


@pytest.mark.asyncio
async def test_service_action_root_has_no_sudo():
    t = FakeTarget({"systemctl stop nginx": (0, "", "")}, username="root")
    await linux.service_action(t, "nginx", "stop")
    assert t.calls == [["systemctl", "stop", "nginx"]]


@pytest.mark.asyncio
async def test_service_action_rejects_unknown_action():
    with pytest.raises(ValueError):
        await linux.service_action(FakeTarget(), "nginx", "disable")


@pytest.mark.asyncio
async def test_hostile_service_name_stays_one_argv_element():
    hostile = "nginx; rm -rf /"
    t = FakeTarget()
    await linux.service_action(t, hostile, "restart")
    assert t.calls[0] == ["systemctl", "restart", hostile]


def test_ssh_target_quotes_every_argv_element(monkeypatch):
    """SSH exec goes through the remote shell; each argv element must be quoted."""
    from agentica.tools.remote.ssh_target import SSHTarget

    sent: list[str] = []

    class _Chan:
        def recv_exit_status(self):
            return 0

    class _Stream:
        channel = _Chan()

        def read(self, n):
            return b""

    class _Client:
        def exec_command(self, cmd, timeout=None):
            sent.append(cmd)
            return None, _Stream(), _Stream()

        def close(self):
            pass

    t = SSHTarget(host="h", trusted_fingerprint="SHA256:x", password="p")
    monkeypatch.setattr(t, "_connect", lambda: _Client())
    t._run_sync(["systemctl", "restart", "nginx; rm -rf /", "$(id)"], timeout=5)
    assert sent == ["systemctl restart 'nginx; rm -rf /' '$(id)'"]


def test_ssh_fingerprint_matching_md5_and_sha256():
    import paramiko
    from agentica.tools.remote.ssh_target import fingerprint_matches, fingerprints

    key = paramiko.Ed25519Key.generate() if hasattr(paramiko.Ed25519Key, "generate") else paramiko.RSAKey.generate(1024)
    fps = fingerprints(key)
    assert fingerprint_matches(key, fps["sha256"])
    assert fingerprint_matches(key, fps["md5"])
    assert fingerprint_matches(key, fps["md5"].replace(":", "").upper())
    assert not fingerprint_matches(key, "SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")


def test_ssh_target_refuses_untrusted_host():
    import paramiko
    from agentica.tools.remote.ssh_target import SSHTarget

    with pytest.raises(paramiko.SSHException):
        SSHTarget(host="127.0.0.1", trusted_fingerprint=None)._connect()
