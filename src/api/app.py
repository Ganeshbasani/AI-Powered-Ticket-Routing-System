"""Flask application factory for the SLA prediction API."""

from __future__ import annotations

import uuid
from pathlib import Path

from flask import Flask, Response, g, jsonify, request, send_from_directory

from src.api.errors import APIError
from src.api.routes import api_blueprint
from src.common.logging_config import configure_logging
from src.config.settings import settings
from src.ml.model import ModelService
from src.persistence.database import Database
from src.persistence.repository import TicketRepository
from src.platform.services import InMemoryRateLimiter, TicketService, TokenService


def create_app(
    model_service: ModelService | None = None,
    database: Database | None = None,
    token_service: TokenService | None = None,
    rate_limiter: InMemoryRateLimiter | None = None,
    rate_limits: dict[str, int] | None = None,
) -> Flask:
    """Create an application with request IDs and safe error responses."""

    logger = configure_logging(settings.log_level)

    frontend_directory = Path(__file__).resolve().parents[2] / "frontend" / "dist"

    # Disable Flask's automatic /app/<filename> static route.
    # Frontend files are served explicitly below.
    app = Flask(__name__, static_folder=None)

    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

    app.extensions["model_service"] = model_service or ModelService()

    database = database or Database(settings.database_path)
    database.initialize()

    repository = TicketRepository(database)

    app.extensions["ticket_repository"] = repository

    app.extensions["ticket_service"] = TicketService(
        repository,
        app.extensions["model_service"],
    )

    app.extensions["token_service"] = token_service or TokenService(
        settings.auth_secret_key
    )

    app.extensions["rate_limiter"] = rate_limiter or InMemoryRateLimiter()

    app.config["RATE_LIMITS"] = rate_limits or {
        "login": settings.login_rate_limit,
        "prediction": settings.prediction_rate_limit,
        "jira_import": settings.jira_import_rate_limit,
    }

    app.register_blueprint(api_blueprint, url_prefix="/api/v1")

    # Serve the frontend entry point.
    @app.get("/")
    def frontend() -> Response:
        return send_from_directory(frontend_directory, "index.html")

    # Serve frontend assets such as:
    # /style.css
    # /app.js
    # /favicon.ico
    @app.get("/<path:filename>")
    def frontend_static(filename: str) -> Response:
        return send_from_directory(frontend_directory, filename)

    app.logger.handlers = logger.handlers
    app.logger.setLevel(logger.level)

    @app.before_request
    def assign_request_id() -> None:
        g.request_id = uuid.uuid4().hex

        limits = {
            "api.login": "login",
            "api.predict": "prediction",
            "api.import_mock_jira_ticket": "jira_import",
        }

        if request.endpoint in limits:
            scope = limits[request.endpoint]
            limit = app.config["RATE_LIMITS"][scope]

            if not app.extensions["rate_limiter"].allow(
                request.remote_addr or "unknown",
                scope,
                limit,
            ):
                raise APIError(
                    "Rate limit exceeded. Try again later.",
                    429,
                    "rate_limited",
                )

    @app.after_request
    def add_request_id(response: Response) -> Response:
        response.headers["X-Request-ID"] = g.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(APIError)
    def handle_api_error(error: APIError) -> tuple[Response, int]:
        app.logger.warning(
            error.code,
            extra={"request_id": g.request_id},
        )

        return (
            jsonify(
                {
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "request_id": g.request_id,
                    }
                }
            ),
            error.status_code,
        )

    @app.errorhandler(413)
    def handle_request_too_large(
        error: Exception,
    ) -> tuple[Response, int]:
        return (
            jsonify(
                {
                    "error": {
                        "code": "request_too_large",
                        "message": "Request body is too large.",
                        "request_id": g.request_id,
                    }
                }
            ),
            413,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(
        error: Exception,
    ) -> tuple[Response, int]:
        app.logger.exception(
            "unexpected_error",
            extra={"request_id": g.request_id},
        )

        return (
            jsonify(
                {
                    "error": {
                        "code": "internal_error",
                        "message": "An internal error occurred.",
                        "request_id": g.request_id,
                    }
                }
            ),
            500,
        )

    app.logger.info(
        "application_started",
        extra={"request_id": None},
    )

    return app

