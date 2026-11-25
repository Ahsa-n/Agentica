"""
Builds tests/fixtures/linux: recorded data of a small Ubuntu 22.04 server (4 CPUs, nginx, postgres)
in the exact formats Linux uses, so linux_remote.py can be tested on Windows.

    python tests/fixtures/make_linux_fixture.py
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "linux"
BTIME = 1795500000                       # boot time (epoch)
NOW = BTIME + 3 * 86400 + 4 * 3600       # 3 d 4 h uptime
CLK = 100
PAGE = 4096


def w(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


shutil.rmtree(ROOT, ignore_errors=True)

# cpu: first sample here, second sample in meta.json -> total 25% busy, cpu2 is the busiest
w("proc/stat", "\n".join([
    "cpu  40000 100 20000 300000 2000 0 500 0 0 0",
    "cpu0 10000 25 5000 75000 500 0 125 0 0 0",
    "cpu1 10000 25 5000 75000 500 0 125 0 0 0",
    "cpu2 10000 25 5000 75000 500 0 125 0 0 0",
    "cpu3 10000 25 5000 75000 500 0 125 0 0 0",
    "intr 123456", "ctxt 987654", f"btime {BTIME}", "processes 4321", "procs_running 2", "procs_blocked 0"]) + "\n")
# second sample (idle, total) 0.5 s later: +400 ticks total, +300 idle -> 25% busy; cpu2 is the busiest (40%)
stat2 = {"cpu": [302000 + 300, 362600 + 400], "cpu0": [75500 + 80, 90650 + 100], "cpu1": [75500 + 80, 90650 + 100],
         "cpu2": [75500 + 60, 90650 + 100], "cpu3": [75500 + 80, 90650 + 100]}

w("proc/meminfo", "\n".join([
    "MemTotal:        8148084 kB", "MemFree:          912340 kB", "MemAvailable:    3074042 kB",
    "Buffers:          182044 kB", "Cached:          2101132 kB", "SwapCached:            0 kB",
    "SwapTotal:       2097148 kB", "SwapFree:        1835004 kB"]) + "\n")
w("proc/uptime", f"{NOW - BTIME}.42 1000000.00\n")
cpuinfo = []
for i, (phys, core) in enumerate([(0, 0), (0, 1), (0, 0), (0, 1)]):      # 4 threads, 2 cores
    cpuinfo += [f"processor\t: {i}", "model name\t: Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz",
                "cpu MHz\t\t: 2399.998", f"physical id\t: {phys}", f"core id\t\t: {core}", ""]
w("proc/cpuinfo", "\n".join(cpuinfo))
w("proc/sys/kernel/osrelease", "5.15.0-91-generic\n")
w("proc/mounts", "\n".join([
    "sysfs /sys sysfs rw,nosuid,nodev,noexec,relatime 0 0", "proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0",
    "/dev/sda2 / ext4 rw,relatime 0 0", "tmpfs /run tmpfs rw,nosuid,nodev,size=814808k 0 0",
    "/dev/sda1 /boot/efi vfat rw,relatime,fmask=0077 0 0", "/dev/sdb1 /srv/data xfs rw,relatime 0 0",
    "/dev/loop0 /snap/core20/2105 squashfs ro,nodev,relatime 0 0", "/dev/sda2 /var/lib/docker ext4 rw,relatime 0 0"]) + "\n")
w("proc/net/dev", "\n".join([
    "Inter-|   Receive                                                |  Transmit",
    " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed",
    "    lo: 5000000   40000    0    0    0     0          0         0  5000000   40000    0    0    0     0       0          0",
    "  eth0: 900000000  700000    0    0    0     0          0         0 300000000  500000    0    0    0     0       0          0"]) + "\n")
w("etc/os-release", 'PRETTY_NAME="Ubuntu 22.04.4 LTS"\nNAME="Ubuntu"\nVERSION_ID="22.04"\nID=ubuntu\n')
w("etc/hostname", "web-01\n")
w("sys/class/net/lo/operstate", "unknown\n")
w("sys/class/net/eth0/operstate", "up\n")
w("sys/class/net/eth0/speed", "1000\n")
w("sys/class/net/docker0/operstate", "down\n")
w("sys/class/net/docker0/speed", "-1\n")

# processes: pid, comm, utime, stime, start ticks after boot, rss pages
procs = [(1, "systemd", 900, 400, 1, 3000), (812, "sshd", 50, 30, 400, 1800),
         (1201, "nginx", 3000, 1200, 500, 2500), (1202, "nginx", 2600, 900, 500, 2300),
         (1350, "postgres", 8000, 2000, 600, 52000), (1351, "postgres", 400, 100, 650, 9000),
         (2001, "python3", 120, 40, 900000, 6000), (2500, "kworker/0:1", 5, 3, 1000, 0)]
for pid, comm, ut, st, start, rss in procs:
    w(f"proc/{pid}/stat", f"{pid} ({comm}) S 1 {pid} {pid} 0 -1 4194560 1000 0 0 0 {ut} {st} 0 0 20 0 1 0 {start} "
                          f"123456789 {rss} 18446744073709551615 0 0 0 0 0 0 0 0 0 0 0 0 17 1 0 0 0 0 0\n")
    w(f"proc/{pid}/statm", f"{rss * 3} {rss} 500 200 0 {rss} 0\n")
    w(f"proc/{pid}/comm", comm + "\n")

SHOW = "--no-pager --property=Id,Description,LoadState,ActiveState,SubState,UnitFileState,MainPID"


def show(unit, desc, active, sub, ufs, pid):
    return f"Id={unit}\nDescription={desc}\nLoadState=loaded\nActiveState={active}\nSubState={sub}\nUnitFileState={ufs}\nMainPID={pid}\n"


commands = {
    rf"systemctl show nginx(\.service)? {SHOW}": [0, show("nginx.service", "A high performance web server and a reverse proxy server", "active", "running", "enabled", 1201), ""],
    rf"systemctl show postgresql(\.service)? {SHOW}": [0, show("postgresql.service", "PostgreSQL RDBMS", "active", "exited", "enabled", 0), ""],
    rf"systemctl show ssh(\.service)? {SHOW}": [0, show("ssh.service", "OpenBSD Secure Shell server", "active", "running", "enabled", 812), ""],
    rf"systemctl show redis-server(\.service)? {SHOW}": [0, show("redis-server.service", "Advanced key-value store", "failed", "failed", "enabled", 0), ""],
    rf"systemctl show .* {SHOW}": [0, "Id=x.service\nLoadState=not-found\nActiveState=inactive\n", ""],
    r"systemctl list-units --type=service --all --no-legend --plain --no-pager": [0, "\n".join([
        "nginx.service loaded active running A high performance web server and a reverse proxy server",
        "postgresql.service loaded active exited PostgreSQL RDBMS",
        "redis-server.service loaded failed failed Advanced key-value store",
        "ssh.service loaded active running OpenBSD Secure Shell server",
        "cron.service loaded active running Regular background program processing daemon",
        "ufw.service loaded inactive dead Uncomplicated firewall"]) + "\n", ""],
    r"systemctl list-units --type=service --all --no-legend --plain --no-pager --state=failed": [0, "redis-server.service loaded failed failed Advanced key-value store\n", ""],
    r"systemctl list-units --type=service --all --no-legend --plain --no-pager --state=running": [0, "nginx.service loaded active running A high performance web server and a reverse proxy server\nssh.service loaded active running OpenBSD Secure Shell server\ncron.service loaded active running Regular background program processing daemon\n", ""],
    r"systemctl list-units --type=service --all --no-legend --plain --no-pager --state=inactive": [0, "ufw.service loaded inactive dead Uncomplicated firewall\n", ""],
    r"systemctl list-dependencies --reverse --plain --no-pager postgresql(\.service)?": [0, "postgresql.service\n  app-backend.service\n  multi-user.target\n", ""],
    r"systemctl list-dependencies --reverse --plain --no-pager .*": [0, "x.service\n  multi-user.target\n", ""],
    r"systemctl is-active app-backend.service": [0, "active\n", ""],
    r"sudo -n true": [0, "", ""],
    r"sudo -n systemctl (start|stop|restart) redis-server": [1, "", "sudo: a password is required\n"],
    r"sudo -S -p  systemctl (start|stop|restart) redis-server": [1, "", "Sorry, user agentica is not allowed to execute '/usr/bin/systemctl start redis-server' as root on web-01.\n"],
    r"ss -ltnpH": [0, "\n".join([
        'LISTEN 0      511          0.0.0.0:80        0.0.0.0:*    users:(("nginx",pid=1202,fd=6),("nginx",pid=1201,fd=6))',
        'LISTEN 0      511          0.0.0.0:443       0.0.0.0:*    users:(("nginx",pid=1202,fd=7),("nginx",pid=1201,fd=7))',
        'LISTEN 0      244        127.0.0.1:5432      0.0.0.0:*    users:(("postgres",pid=1350,fd=5))',
        'LISTEN 0      128          0.0.0.0:22        0.0.0.0:*    users:(("sshd",pid=812,fd=3))',
        'LISTEN 0      128             [::]:22           [::]:*    users:(("sshd",pid=812,fd=4))']) + "\n", ""],
    r"ip -4 -o addr show": [0, "1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever preferred_lft forever\n"
                               "2: eth0    inet 10.0.0.21/24 brd 10.0.0.255 scope global eth0\\       valid_lft forever preferred_lft forever\n", ""],
}
(ROOT / "commands.json").write_text(json.dumps(commands, indent=1), encoding="utf-8")

meta = {
    "ncpu": 4, "now": NOW, "stat2": stat2,
    "cpu": {"1201": 3.5, "1202": 2.5, "1350": 12.0, "1351": 0.5, "2001": 0.2},
    "netdev2": [900000000 + 625000, 300000000 + 125000],          # +10 Mb/s rx, +2 Mb/s tx over 0.5 s
    "statvfs": {"/": {"total": 100 * 1024 ** 3, "free": 38 * 1024 ** 3},
                "/boot/efi": {"total": 512 * 1024 ** 2, "free": 500 * 1024 ** 2},
                "/srv/data": {"total": 500 * 1024 ** 3, "free": 20 * 1024 ** 3}},
}
(ROOT / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
print("fixture written to", ROOT)
