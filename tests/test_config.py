"""Tests for environment configuration validation."""

from __future__ import annotations

import pytest
import socket

from src.config.settings import ConfigurationError, Settings
from src.api.local_runner import find_local_port


def test_settings_have_safe_defaults(tmp_path):
    settings = Settings.from_environment({}, base_dir=tmp_path)

    assert settings.flask_debug is False
    assert settings.flask_port == 5000
    assert settings.environment == "development"
    assert settings.priority_map["Critical"] == 3


def test_settings_honor_platform_port_and_allow_external_persistent_database(tmp_path):
    mount_path = tmp_path.parent / "mounted" / "platform.db"
    settings = Settings.from_environment(
        {"PORT": "8123", "DATABASE_PATH": str(mount_path)}, base_dir=tmp_path
    )
    assert settings.flask_port == 8123
    assert settings.database_path == mount_path.resolve()


def test_local_runner_selects_a_free_port_when_the_configured_port_is_busy():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        occupied_port = listener.getsockname()[1]
        selected_port = find_local_port("127.0.0.1", occupied_port, attempts=10)

    assert selected_port != occupied_port
    assert occupied_port < selected_port <= occupied_port + 10


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
