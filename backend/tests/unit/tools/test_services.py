"""Unit tests for service tools."""

from __future__ import annotations

import pytest

from agentica.tools.base import RiskTier
from agentica.tools.local.services import (
    GetServiceStatus,
    ListServices,
    RestartService,
    ServiceNameInput,
    StartService,
    StopService,
)


def test_read_tools_are_read_tier():
    assert GetServiceStatus.spec.risk_tier == RiskTier.READ
    assert ListServices.spec.risk_tier == RiskTier.READ


def test_modify_tools_are_modify_tier():
    assert StartService.spec.risk_tier == RiskTier.MODIFY
    assert RestartService.spec.risk_tier == RiskTier.MODIFY


def test_stop_service_is_destructive():
    assert StopService.spec.risk_tier == RiskTier.DESTRUCTIVE


def test_service_name_input_forbids_extra():
    with pytest.raises(Exception):
        ServiceNameInput.model_validate({"name": "nginx", "extra_field": "bad"})


def test_service_tools_have_names():
    for cls in [GetServiceStatus, ListServices, StartService, RestartService, StopService]:
        assert cls.spec.name


def test_all_registered():
    from agentica.tools.registry import registry
    for name in ["get_service_status", "list_services", "start_service", "restart_service", "stop_service"]:
        assert name in registry
