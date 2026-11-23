"""Egress guard tests — local mode zero egress."""

from __future__ import annotations

import pytest
from agentica.config.egress_guard import is_local_allowed, check_egress


def test_localhost_allowed():
    assert is_local_allowed("http://localhost:11434/api/chat")
    assert is_local_allowed("http://127.0.0.1:11434")
    assert is_local_allowed("https://127.0.0.1:5432")


def test_external_blocked():
    assert not is_local_allowed("https://api.openai.com/v1/chat")
    assert not is_local_allowed("https://huggingface.co/models")
    assert not is_local_allowed("https://smith.langchain.com")


def test_check_egress_raises_in_local_mode():
    with pytest.raises(RuntimeError, match="Egress blocked"):
        check_egress("https://api.openai.com/v1/chat", mode="local")


def test_check_egress_ok_localhost_local_mode():
    check_egress("http://localhost:11434", mode="local")  # should not raise


def test_check_egress_passthrough_cloud_mode():
    check_egress("https://api.openai.com/v1/chat", mode="cloud")  # should not raise
