"""Flask application factory for the SLA prediction API."""

from __future__ import annotations

import uuid
import os
from pathlib import Path

from flask import Flask, Response, g, jsonify, request, send_from_directory

from src.api.errors import APIError
from src.api.routes import api_blueprint
from src.common.logging_config import configure_logging
from src.config.settings import settings
from src.ml.model import ModelService
from src.ml.candidate_service import CandidateModelService
from src.persistence.database import Database
from src.persistence.repository import TicketRepository
from src.platform.services import InMemoryRateLimiter, TicketService, TokenService
from src.platform.demo import setup_demo_account
from src.platform.support_bot import ProjectSupportBot
from src.platform.local_llm import LocalOllamaChat


def create_app(
    model_service: ModelService | None = None,
    candidate_model_service: CandidateModelService | None = None,
    database: Database | None = None,
    token_service: TokenService | None = None,
    rate_limiter: InMemoryRateLimiter | None = None,
    rate_limits: dict[str, int] | None = None,
) -> Flask:

    logger = configure_logging(settings.log_level)

    frontend_root = Path(__file__).resolve().parents[2] / "frontend"
    built_frontend = frontend_root / "dist"
    source_frontend = frontend_root / "src"
    # A repository checkout can run directly without a separate frontend build.
    # Production images still prefer the deterministic build-stage output.
    frontend_directory = (
        source_frontend
        if settings.environment in {"development", "test"} and source_frontend.is_dir()
        else built_frontend if built_frontend.is_dir() else source_frontend
    )

    app = Flask(__name__)

    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024
    app.config["DEMO_ADMIN_EMAIL"] = os.environ.get("DEMO_ADMIN_EMAIL", "").strip()
    app.config["DEMO_ADMIN_PASSWORD"] = os.environ.get("DEMO_ADMIN_PASSWORD", "")

    app.extensions["model_service"] = model_service or ModelService()
    app.extensions["candidate_model_service"] = candidate_model_service or CandidateModelService()

    seed_configured_demo = database is None
    database = database or Database(settings.database_path)
    database.initialize()

    repository = TicketRepository(database)

    demo_email = os.environ.get("DEMO_ADMIN_EMAIL", "").strip()
    demo_password = os.environ.get("DEMO_ADMIN_PASSWORD", "")
    if bool(demo_email) != bool(demo_password):
        raise RuntimeError("Set both DEMO_ADMIN_EMAIL and DEMO_ADMIN_PASSWORD to enable demo setup.")
    if seed_configured_demo and demo_email and demo_password:
        setup_demo_account(repository, demo_email, demo_password)

    app.extensions["ticket_repository"] = repository
    app.extensions["local_support_llm"] = LocalOllamaChat()
    app.extensions["project_support_bot"] = ProjectSupportBot(local_llm=app.extensions["local_support_llm"])
    app.extensions["ticket_service"] = TicketService(
        repository,
        app.extensions["model_service"],
    )

    app.extensions["token_service"] = (
        token_service or TokenService(settings.auth_secret_key)
    )

    app.extensions["rate_limiter"] = (
        rate_limiter or InMemoryRateLimiter()
    )

    app.config["RATE_LIMITS"] = rate_limits or {
        "login": settings.login_rate_limit,
        "prediction": settings.prediction_rate_limit,
        "jira_import": settings.jira_import_rate_limit,
    }

    app.register_blueprint(
        api_blueprint,
        url_prefix="/api/v1",
    )

    @app.get("/")
    def frontend() -> Response:
        return send_from_directory(
            frontend_directory,
            "index.html",
        )

    @app.get("/app.js")
    def frontend_js() -> Response:
        return send_from_directory(
            frontend_directory,
            "app.js",
        )

    @app.get("/style.css")
    def frontend_css() -> Response:
        return send_from_directory(
            frontend_directory,
            "style.css",
        )

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status=204)

    app.logger.handlers = logger.handlers
    app.logger.setLevel(logger.level)

    @app.before_request
    def assign_request_id() -> None:
        g.request_id = uuid.uuid4().hex

        limits = {
            "api.login": "login",
            "api.predict": "prediction",
            "api.experimental_ticket_prediction": "prediction",
            "api.support_chat": "prediction",
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
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'"
        )
        return response

    @app.errorhandler(APIError)
    def handle_api_error(
        error: APIError,
    ) -> tuple[Response, int]:

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
