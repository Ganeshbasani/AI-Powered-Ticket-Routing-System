"""Validated application configuration loaded from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

DEFAULT_PRIORITY_MAP = {"Low": 0, "Medium": 1, "High": 2}
VALID_ENVIRONMENTS = {"development", "test", "production"}
VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class ConfigurationError(ValueError):
    """Raised when environment configuration is invalid or unsafe."""


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ConfigurationError(f"{name} must be a boolean value.")


def _workspace_path(value: str, name: str, base_dir: Path) -> Path:
    candidate = Path(value)
    resolved = (base_dir / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        resolved.relative_to(base_dir.resolve())
    except ValueError as error:
        raise ConfigurationError(f"{name} must be located inside the application directory.") from error
    return resolved


@dataclass(frozen=True)
class Settings:
    """Configuration values safe to use throughout the application."""

    model_path: Path
    data_path: Path
    database_path: Path
    flask_host: str
    flask_port: int
    flask_debug: bool
    log_level: str
    environment: str
    auth_secret_key: str | None
    login_rate_limit: int
    prediction_rate_limit: int
    jira_import_rate_limit: int
    priority_map: dict[str, int]

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        base_dir: Path = BASE_DIR,
    ) -> "Settings":
        values = os.environ if environment is None else environment
        app_environment = values.get("APP_ENV", "development").lower()
        if app_environment not in VALID_ENVIRONMENTS:
            raise ConfigurationError("APP_ENV must be development, test, or production.")

        try:
            flask_port = int(values.get("FLASK_PORT", "5000"))
        except ValueError as error:
            raise ConfigurationError("FLASK_PORT must be an integer.") from error
        if not 1 <= flask_port <= 65535:
            raise ConfigurationError("FLASK_PORT must be between 1 and 65535.")

        flask_debug = _parse_bool(values.get("FLASK_DEBUG", "False"), "FLASK_DEBUG")
        if app_environment == "production" and flask_debug:
            raise ConfigurationError("FLASK_DEBUG cannot be enabled in production.")
        auth_secret_key = values.get("AUTH_SECRET_KEY")
        if app_environment == "production" and not auth_secret_key:
            raise ConfigurationError("AUTH_SECRET_KEY is required in production.")

        log_level = values.get("LOG_LEVEL", "INFO").upper()
        if log_level not in VALID_LOG_LEVELS:
            raise ConfigurationError("LOG_LEVEL must be a standard Python log level.")
        def positive(name: str, default: str) -> int:
            try: value = int(values.get(name, default))
            except ValueError as error: raise ConfigurationError(f"{name} must be an integer.") from error
            if value < 1: raise ConfigurationError(f"{name} must be positive.")
            return value

        return cls(
            model_path=_workspace_path(
                values.get("MODEL_PATH", "ml_model/sla_model.joblib"), "MODEL_PATH", base_dir
            ),
            data_path=_workspace_path(values.get("DATA_PATH", "data/tickets.csv"), "DATA_PATH", base_dir),
            database_path=_workspace_path(values.get("DATABASE_PATH", "data/platform.db"), "DATABASE_PATH", base_dir),
            flask_host=values.get("FLASK_HOST", "0.0.0.0"),
            flask_port=flask_port,
            flask_debug=flask_debug,
            log_level=log_level,
            environment=app_environment,
            auth_secret_key=auth_secret_key,
            login_rate_limit=positive("LOGIN_RATE_LIMIT", "10"),
            prediction_rate_limit=positive("PREDICTION_RATE_LIMIT", "60"),
            jira_import_rate_limit=positive("JIRA_IMPORT_RATE_LIMIT", "20"),
            priority_map=DEFAULT_PRIORITY_MAP.copy(),
        )


settings = Settings.from_environment()
