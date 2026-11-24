"""Config loader tests."""

from __future__ import annotations

import pytest

from agentica.config.loader import Settings, _check_no_secrets
from agentica.config.secrets import redact


def test_redact_password_in_text():
    text = "password: mysecret123"
    assert "mysecret123" not in redact(text)


def test_redact_bearer_token():
    text = "Authorization: Bearer abc123XYZtoken"
    assert "abc123XYZtoken" not in redact(text)


def test_settings_defaults():
    settings = Settings()
    assert settings.app.host == "127.0.0.1"
    assert settings.llm.mode == "local"
    assert settings.agent.max_steps == 10


def test_check_no_secrets_raises_on_password_key():
    with pytest.raises(ValueError, match="secret"):
        _check_no_secrets({"password": "abc"})


def test_check_no_secrets_nested():
    with pytest.raises(ValueError):
        _check_no_secrets({"db": {"secret_key": "abc"}})


def test_check_no_secrets_ok():
    _check_no_secrets({"app": {"name": "Agentica"}, "db": {"host": "localhost"}})


def test_local_mode_requires_no_cloud_provider():
    s = Settings.model_validate({"llm": {"mode": "local"}})
    assert s.llm.cloud_provider is None
