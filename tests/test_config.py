"""Tests for environment configuration validation."""

from __future__ import annotations

import pytest

from src.config.settings import ConfigurationError, Settings


def test_settings_have_safe_defaults(tmp_path):
    settings = Settings.from_environment({}, base_dir=tmp_path)

    assert settings.flask_debug is False
    assert settings.flask_port == 5000
    assert settings.environment == "development"


@pytest.mark.parametrize(
    "environment",
    [
        {"FLASK_PORT": "not-a-port"},
        {"FLASK_PORT": "70000"},
        {"FLASK_DEBUG": "maybe"},
        {"APP_ENV": "production", "FLASK_DEBUG": "true"},
        {"MODEL_PATH": "C:/outside/model.joblib"},
    ],
)
def test_settings_reject_invalid_or_unsafe_values(tmp_path, environment):
    with pytest.raises(ConfigurationError):
        Settings.from_environment(environment, base_dir=tmp_path)
