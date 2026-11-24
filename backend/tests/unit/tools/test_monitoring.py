"""Unit tests for monitoring tools."""

from __future__ import annotations

import pytest

from agentica.tools.base import RiskTier
from agentica.tools.local.monitoring import (
    EmptyInput,
    GetCPUUsage,
    GetDiskUsage,
    GetMemoryUsage,
    GetNetworkStats,
    GetProcessDetails,
    GetSystemOverview,
    ListTopProcesses,
    PidInput,
    TopProcessesInput,
)


@pytest.mark.asyncio
async def test_get_system_overview():
    tool = GetSystemOverview()
    result = await tool.run(EmptyInput())
    assert result.hostname
    assert result.cpu.percent >= 0
    assert result.memory.total_gb > 0
    assert isinstance(result.disk.partitions, list)


@pytest.mark.asyncio
async def test_get_cpu_usage():
    tool = GetCPUUsage()
    result = await tool.run(EmptyInput())
    assert 0 <= result.percent <= 100
    assert result.core_count >= 1


@pytest.mark.asyncio
async def test_get_memory_usage():
    tool = GetMemoryUsage()
    result = await tool.run(EmptyInput())
    assert result.total_gb > 0
    assert result.percent >= 0


@pytest.mark.asyncio
async def test_get_disk_usage():
    tool = GetDiskUsage()
    result = await tool.run(EmptyInput())
    assert isinstance(result.partitions, list)
    assert len(result.partitions) >= 1


@pytest.mark.asyncio
async def test_get_network_stats():
    tool = GetNetworkStats()
    result = await tool.run(EmptyInput())
    assert isinstance(result.interfaces, list)


@pytest.mark.asyncio
async def test_list_top_processes():
    tool = ListTopProcesses()
    result = await tool.run(TopProcessesInput(limit=5))
    assert len(result.processes) <= 5


@pytest.mark.asyncio
async def test_get_process_details_invalid_pid():
    tool = GetProcessDetails()
    result = await tool.run(PidInput(pid=999999999))
    assert result.status == "not found"


def test_all_monitoring_tools_are_read():
    for tool_cls in [GetSystemOverview, GetCPUUsage, GetMemoryUsage,
                     GetDiskUsage, GetNetworkStats, ListTopProcesses, GetProcessDetails]:
        assert tool_cls.spec.risk_tier == RiskTier.READ


def test_tools_have_pydantic_input_schemas():
    for tool_cls in [GetSystemOverview, GetCPUUsage, GetMemoryUsage,
                     GetDiskUsage, GetNetworkStats, ListTopProcesses, GetProcessDetails]:
        schema = tool_cls.spec.input_schema
        assert "type" in schema or "properties" in schema


def test_tool_spec_has_category():
    from agentica.tools.base import ToolCategory
    for tool_cls in [GetSystemOverview, GetCPUUsage, GetMemoryUsage]:
        assert tool_cls.spec.category == ToolCategory.MONITORING
