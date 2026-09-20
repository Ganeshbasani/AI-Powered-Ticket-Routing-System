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
    ],
)
def test_settings_reject_invalid_or_unsafe_values(tmp_path, environment):
    with pytest.raises(ConfigurationError):
        Settings.from_environment(environment, base_dir=tmp_path)


def test_settings_reject_model_path_outside_workspace(tmp_path):
    outside_model = tmp_path.parent / "outside-model.joblib"
    with pytest.raises(ConfigurationError):
        Settings.from_environment({"MODEL_PATH": str(outside_model)}, base_dir=tmp_path)


def test_production_disables_runtime_model_training_by_default(tmp_path):
    settings = Settings.from_environment(
        {"APP_ENV": "production", "AUTH_SECRET_KEY": "test-secret"},
        base_dir=tmp_path,
    )

    assert settings.allow_model_training is False


def test_runtime_model_training_can_be_enabled_explicitly_for_development(tmp_path):
    settings = Settings.from_environment(
        {"APP_ENV": "development", "ALLOW_MODEL_TRAINING": "false"},
        base_dir=tmp_path,
    )

    assert settings.allow_model_training is False
