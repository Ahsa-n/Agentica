"""Windows remote collectors: PowerShell escaping (injection) and JSON fixtures."""

from __future__ import annotations

import json

import pytest

from agentica.tools.base import FakeTarget
from agentica.tools.remote import windows
from agentica.tools.remote.winrm_target import ps_quote

# ─── PowerShell escaping helper ──────────────────────────────────────────────

INJECTION_CASES = [
    "Spooler'; Remove-Item C:\\ -Recurse; '",
    "x' + (Invoke-Expression 'calc') + '",
    "$(Stop-Computer)",
    "`$env:PATH",
    "name\u2019; Stop-Computer; \u2018",   # Unicode right/left single quotes
    "a\u201aSTOP\u201b",
]


@pytest.mark.parametrize("value", INJECTION_CASES)
def test_ps_quote_produces_a_single_closed_literal(value):
    q = ps_quote(value)
    assert q.startswith("'") and q.endswith("'")
    inner = q[1:-1]
    # Every quote-family character inside the literal must be doubled (escaped).
    for ch in ("'", "\u2018", "\u2019", "\u201a", "\u201b"):
        i = 0
        while i < len(inner):
            if inner[i] == ch:
                assert inner[i + 1:i + 2] == ch, f"unescaped {ch!r} in {q!r}"
                i += 2
            else:
                i += 1


def test_ps_quote_plain_value_unchanged():
    assert ps_quote("Spooler") == "'Spooler'"


# ─── Parsers ─────────────────────────────────────────────────────────────────

def test_as_list_normalises_single_object():
    assert windows.as_list({"a": 1}) == [{"a": 1}]
    assert windows.as_list([1, 2]) == [1, 2]
    assert windows.as_list(None) == []


def test_parse_cpu():
    r = windows.parse_cpu({"Load": 23, "Cores": 4, "PerCpu": [10, 20, 30, 32]})
    assert r.percent == 23.0 and r.core_count == 4 and r.per_cpu == [10.0, 20.0, 30.0, 32.0]


def test_parse_memory_kb():
    r = windows.parse_memory({"TotalVisibleMemorySize": 8_000_000, "FreePhysicalMemory": 2_000_000,
                              "TotalVirtualMemorySize": 10_000_000, "FreeVirtualMemory": 3_000_000})
    assert r.percent == 75.0
    assert r.total_gb == round(8_000_000 * 1024 / 1e9, 2)
    assert r.swap_total_gb == round(2_000_000 * 1024 / 1e9, 2)


def test_parse_disk_single_object():
    r = windows.parse_disk({"DeviceID": "C:", "VolumeName": "OS", "FileSystem": "NTFS",
                            "Size": 100e9, "FreeSpace": 25e9})
    assert len(r.partitions) == 1
    assert r.partitions[0].percent == 75.0 and r.partitions[0].free_gb == 25.0


def test_parse_processes_strips_instance_suffix():
    procs = windows.parse_processes([{"Id": 10, "Name": "python#2", "Cpu": 1.5, "Mem": 3.2},
                                     {"Id": 11, "Name": "svchost", "Cpu": 0, "Mem": 0.1}])
    assert [p.name for p in procs] == ["python", "svchost"]


def test_service_state_mapping():
    assert windows.service_state("Running") == "active"
    assert windows.service_state("Stopped") == "inactive"
    assert windows.service_state(None) == "unknown"


# ─── Collectors over a fake WinRM target ─────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_collector():
    data = {"TotalVisibleMemorySize": 4_000_000, "FreePhysicalMemory": 1_000_000,
            "TotalVirtualMemorySize": 4_000_000, "FreeVirtualMemory": 1_000_000}
    t = FakeTarget({windows.MEMORY_PS: (0, json.dumps(data), "")}, os_family="windows")
    r = await windows.memory(t)
    assert r.percent == 75.0


@pytest.mark.asyncio
async def test_service_status_quotes_name():
    hostile = "Spooler'; Stop-Computer; '"
    t = FakeTarget(os_family="windows")
    status, _, _ = await windows.service_status(t, hostile)
    script = t.calls[0][1]
    assert ps_quote(hostile) in script
    assert "-Name 'Spooler''; Stop-Computer; '''" in script
    assert status == "unknown"  # fake returned no output


@pytest.mark.asyncio
async def test_service_action_uses_fixed_verbs():
    t = FakeTarget({"Restart-Service -Name 'Spooler' -ErrorAction Stop": (0, "", "")}, os_family="windows")
    ok, msg = await windows.service_action(t, "Spooler", "restart")
    assert ok and msg == "OK"
    with pytest.raises(ValueError):
        await windows.service_action(t, "Spooler", "Remove")


@pytest.mark.asyncio
async def test_failed_powershell_raises():
    t = FakeTarget({windows.DISK_PS: (1, "", "Access is denied")}, os_family="windows")
    with pytest.raises(windows.RemoteCommandError):
        await windows.disk(t)
