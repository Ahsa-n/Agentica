"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest

# Set env vars before any imports
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


@pytest.fixture(scope="session")
def event_loop_policy():
    """psycopg3 async cannot run on Windows' default ProactorEventLoop."""
    import asyncio
    import sys
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def fake_target():
    from agentica.tools.base import FakeTarget
    return FakeTarget()


@pytest.fixture
def policy_engine():
    from agentica.policy.engine import PolicyEngine
    return PolicyEngine()
