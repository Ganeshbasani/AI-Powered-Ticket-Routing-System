"""HTTP boundary for platform, ticket, and prediction services."""

from __future__ import annotations

import math
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, current_app, g, request
from werkzeug.security import check_password_hash

from src.api.errors import APIError
from src.config.settings import settings
from src.platform.services import AuthenticationError, MockJiraProvider, ROLES

api_blueprint = Blueprint("api", __name__)


def _extensions(name: str):
    return current_app.extensions[name]


def _payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("Request body must be a JSON object.")
    return payload


def _ticket_fields(payload: dict[str, Any]) -> dict[str, Any]:
    required = {"summary", "priority", "created_hours"}
    if not required.issubset(payload):
        raise APIError("Missing required fields: summary, priority, created_hours.")
    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise APIError("Field 'summary' must be a non-empty string.")
    if payload["priority"] not in settings.priority_map:
        raise APIError("Field 'priority' must be a supported priority.")
    try:
        if isinstance(payload["created_hours"], bool):
            raise ValueError
        age = float(payload["created_hours"])
    except (TypeError, ValueError) as error:
        raise APIError("Field 'created_hours' must be a number.") from error
    if not math.isfinite(age) or age < 0:
        raise APIError("Field 'created_hours' must be a finite, non-negative number.")
    return {**payload, "created_hours": age}


def require_roles(*roles: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                raise APIError("Authentication is required.", 401, "authentication_required")
            try:
                claims = _extensions("token_service").verify(header[7:])
            except AuthenticationError as error:
                raise APIError(str(error), 401, "authentication_failed") from error
            user = _extensions("ticket_repository").get_user_by_id(claims["id"])
            if not user or user.get("disabled") or user["role"] not in roles:
                raise APIError("You do not have permission for this action.", 403, "forbidden")
            g.current_user = user
            return view(*args, **kwargs)
        return wrapped
    return decorator


@api_blueprint.get("/health")
def health():
    return {"status": "ok", "request_id": g.request_id}, 200


@api_blueprint.get("/ready")
def readiness():
    ready, _ = _extensions("model_service").readiness()
    return {"status": "ready" if ready else "not_ready", "request_id": g.request_id}, 200 if ready else 503


@api_blueprint.post("/predict")
def predict():
    payload = _payload()
    unknown = set(payload) - {"priority", "created_hours"}
    if unknown:
        raise APIError(f"Unknown field(s): {', '.join(sorted(unknown))}.")
    fields = _ticket_fields({**payload, "summary": "direct prediction"})
    prediction = _extensions("model_service").predict(fields["priority"], fields["created_hours"])
    return {**prediction, "request_id": g.request_id}, 200


@api_blueprint.post("/auth/login")
def login():
    payload = _payload(); email = payload.get("email"); password = payload.get("password")
    user = _extensions("ticket_repository").get_user_by_email(email) if isinstance(email, str) else None
    if not user or user.get("disabled") or not isinstance(password, str) or not check_password_hash(user["password_hash"], password):
        _extensions("ticket_repository").audit(email if isinstance(email, str) else None, "login_failed", "user", None)
        raise APIError("Invalid email or password.", 401, "authentication_failed")
    token = _extensions("token_service").issue(user)
    _extensions("ticket_repository").audit(user["email"], "login", "user", str(user["id"]))
    return {"access_token": token, "token_type": "Bearer", "role": user["role"], "request_id": g.request_id}, 200


@api_blueprint.get("/users")
@require_roles("admin")
def list_users():
    return {"users": _extensions("ticket_repository").list_users(), "request_id": g.request_id}, 200


@api_blueprint.post("/users")
@require_roles("admin")
def create_user():
    payload = _payload(); email, password, role = payload.get("email"), payload.get("password"), payload.get("role")
    if not isinstance(email, str) or not isinstance(password, str) or len(password) < 8 or role not in ROLES:
        raise APIError("email, password (at least 8 characters), and a valid role are required.")
    try:
        user = _extensions("ticket_repository").create_user(email, password, role)
    except Exception as error:
        raise APIError("A user with that email already exists.") from error
    _extensions("ticket_repository").audit(g.current_user["email"], "user_created", "user", str(user["id"]))
    user.pop("password_hash", None)
    return {"user": user, "request_id": g.request_id}, 201


@api_blueprint.patch("/users/<int:user_id>")
@require_roles("admin")
def update_user(user_id: int):
    payload = _payload(); role = payload.get("role"); disabled = payload.get("disabled"); password = payload.get("password")
    if role is not None and role not in ROLES: raise APIError("role is invalid.")
    if disabled is not None and not isinstance(disabled, bool): raise APIError("disabled must be a boolean.")
    if password is not None and (not isinstance(password, str) or len(password) < 8): raise APIError("password must be at least 8 characters.")
    user = _extensions("ticket_repository").update_user(user_id, role=role, disabled=disabled, password=password)
    if not user: raise APIError("User not found.", 404, "not_found")
    action = "user_updated" if disabled is None else ("user_disabled" if disabled else "user_enabled")
    _extensions("ticket_repository").audit(g.current_user["email"], action, "user", str(user_id))
    user.pop("password_hash", None)
    return {"user": user, "request_id": g.request_id}, 200


@api_blueprint.post("/tickets")
@require_roles("admin", "support_agent")
def create_ticket():
    ticket = _extensions("ticket_repository").upsert_ticket(_ticket_fields(_payload()))
    _extensions("ticket_repository").audit(g.current_user["email"], "ticket_created", "ticket", str(ticket["id"]))
    return {"ticket": ticket, "request_id": g.request_id}, 201


@api_blueprint.get("/tickets")
@require_roles("admin", "analyst", "support_agent")
def list_tickets():
    try:
        limit = min(max(int(request.args.get("limit", 20)), 1), 100); offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError as error:
        raise APIError("limit and offset must be integers.") from error
    priority = request.args.get("priority"); status = request.args.get("status"); team = request.args.get("team"); search = request.args.get("search")
    if priority and priority not in settings.priority_map: raise APIError("priority filter is invalid.")
    repository = _extensions("ticket_repository")
    tickets = repository.list_tickets(limit, offset, priority, status, team, search)
    return {"tickets": tickets, "limit": limit, "offset": offset, "total": repository.ticket_count(priority, status, team, search), "request_id": g.request_id}, 200


@api_blueprint.get("/tickets/<int:ticket_id>")
@require_roles("admin", "analyst", "support_agent")
def get_ticket(ticket_id: int):
    ticket = _extensions("ticket_repository").get_ticket(ticket_id)
    if not ticket: raise APIError("Ticket not found.", 404, "not_found")
    return {"ticket": ticket, "request_id": g.request_id}, 200


@api_blueprint.patch("/tickets/<int:ticket_id>")
@require_roles("admin", "support_agent")
def update_ticket(ticket_id: int):
    payload = _payload()
    allowed = {"summary", "description", "priority", "created_hours", "assigned_team", "status"}
    if not payload or set(payload) - allowed:
        raise APIError("Only supported ticket fields may be updated.")
    current = _extensions("ticket_repository").get_ticket(ticket_id)
    if not current:
        raise APIError("Ticket not found.", 404, "not_found")
    merged = {**current, **payload}
    validated = _ticket_fields(merged)
    ticket = _extensions("ticket_repository").update_ticket(ticket_id, validated)
    _extensions("ticket_repository").audit(g.current_user["email"], "ticket_updated", "ticket", str(ticket_id))
    return {"ticket": ticket, "request_id": g.request_id}, 200


@api_blueprint.get("/analytics")
@require_roles("admin", "analyst")
def analytics():
    return {"analytics": _extensions("ticket_repository").analytics(), "request_id": g.request_id}, 200


@api_blueprint.post("/tickets/<int:ticket_id>/predict")
@require_roles("admin", "support_agent")
def predict_ticket(ticket_id: int):
    prediction = _extensions("ticket_service").predict(ticket_id)
    if not prediction: raise APIError("Ticket not found.", 404, "not_found")
    _extensions("ticket_repository").audit(g.current_user["email"], "ticket_predicted", "ticket", str(ticket_id))
    return {"prediction": prediction, "request_id": g.request_id}, 201


@api_blueprint.get("/tickets/<int:ticket_id>/predictions")
@require_roles("admin", "analyst", "support_agent")
def prediction_history(ticket_id: int):
    if not _extensions("ticket_repository").get_ticket(ticket_id): raise APIError("Ticket not found.", 404, "not_found")
    return {"predictions": _extensions("ticket_repository").predictions_for_ticket(ticket_id), "request_id": g.request_id}, 200


@api_blueprint.post("/integrations/jira/import")
@require_roles("admin")
def import_mock_jira_ticket():
    issue = _payload().get("issue")
    try:
        ticket_fields = _ticket_fields(MockJiraProvider().map_issue(issue))
    except ValueError as error:
        raise APIError(str(error)) from error
    ticket = _extensions("ticket_repository").upsert_ticket(ticket_fields)
    _extensions("ticket_repository").audit(g.current_user["email"], "jira_mock_import", "ticket", str(ticket["id"]))
    return {"ticket": ticket, "request_id": g.request_id}, 200
