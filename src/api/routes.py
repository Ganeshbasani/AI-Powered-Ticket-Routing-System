"""HTTP boundary for platform, ticket, and prediction services."""

from __future__ import annotations

import math
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, current_app, g, request
from werkzeug.security import check_password_hash

from src.api.errors import APIError
from src.config.settings import settings
from src.ml.candidate_service import CandidateArtifactError
from src.platform.services import AuthenticationError, MockJiraProvider, ROLES
from src.ml.sla_policy import assess_sla, policy_description

api_blueprint = Blueprint("api", __name__)


def _extensions(name: str):
    return current_app.extensions[name]


def _payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("Request body must be a JSON object.")
    return payload


def _ticket_fields(payload: dict[str, Any], *, require_age: bool = True) -> dict[str, Any]:
    required = {"summary", "priority"} | ({"created_hours"} if require_age else set())
    if not required.issubset(payload):
        raise APIError("Missing required fields: " + ", ".join(sorted(required - set(payload))) + ".")
    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise APIError("Field 'summary' must be a non-empty string.")
    if len(payload["summary"].strip()) > 240:
        raise APIError("Field 'summary' must be at most 240 characters.")
    if payload.get("description") is not None and not isinstance(payload.get("description"), str):
        raise APIError("Field 'description' must be text.")
    if payload.get("assigned_team") is not None and not isinstance(payload.get("assigned_team"), str):
        raise APIError("Field 'assigned_team' must be text.")
    if payload.get("status") is not None and (not isinstance(payload.get("status"), str) or not payload["status"].strip()):
        raise APIError("Field 'status' must be non-empty text.")
    if payload["priority"] not in settings.priority_map:
        supported = ", ".join(settings.priority_map)
        raise APIError(f"Field 'priority' must be one of: {supported}.")
    try:
        if isinstance(payload.get("created_hours", 0), bool):
            raise ValueError
        age = float(payload.get("created_hours", 0))
    except (TypeError, ValueError) as error:
        raise APIError("Field 'created_hours' must be a number.") from error
    if not math.isfinite(age) or age < 0:
        raise APIError("Field 'created_hours' must be a finite, non-negative number.")
    return {**payload, "created_hours": age}


def _store_ml_assessment(ticket: dict[str, Any]) -> dict[str, Any]:
    """Persist model suggestions when a checksum-verified artifact is available."""
    repository = _extensions("ticket_repository")
    try:
        result = _extensions("candidate_model_service").predict(ticket)
    except (CandidateArtifactError, ValueError) as error:
        return {"status": "unavailable", "message": str(error), "review_required": True}
    stored = repository.add_ml_assessment(int(ticket["id"]), result)
    status = "observed" if result.get("data_origin") == "observed" else "experimental"
    return {"status": status, **stored}


def _ticket_with_live_sla(ticket: dict[str, Any]) -> dict[str, Any]:
    return {**ticket, "sla_assessment": assess_sla(ticket["priority"], ticket["created_hours"])}


def _dashboard_sla(analytics: dict[str, Any]) -> dict[str, Any]:
    repository = _extensions("ticket_repository")
    active = repository.active_tickets()
    evaluated = [_ticket_with_live_sla(ticket) for ticket in active]
    alerting = [item for item in evaluated if item["sla_assessment"]["sla_breach_risk"] == "High"]
    analytics["active_breached_tickets"] = sum(item["sla_assessment"]["sla_status"] == "Breached" for item in evaluated)
    analytics["active_approaching_tickets"] = sum(item["sla_assessment"]["sla_status"] == "Approaching target" for item in evaluated)
    analytics["active_high_risk_tickets"] = len(alerting)
    analytics["sla_alerts"] = [
        {"id": item["id"], "summary": item["summary"], "priority": item["priority"],
         "status": item["status"], "assigned_team": item["assigned_team"],
         **item["sla_assessment"]}
        for item in sorted(alerting, key=lambda entry: (entry["sla_assessment"]["sla_status"] != "Breached", entry["sla_assessment"]["remaining_hours"]))[:20]
    ]
    # Keep the dashboard's historical metric and add a distinct live count.
    analytics["predicted_breaches"] = analytics["active_high_risk_tickets"]
    return analytics


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


@api_blueprint.post("/support/chat")
def support_chat():
    payload = _payload()
    if not set(payload).issubset({"message", "history", "ticket_id"}) or "message" not in payload:
        raise APIError("Request body must contain a message and optional chat history and ticket ID.")
    message = payload.get("message")
    if not isinstance(message, str):
        raise APIError("message must be a string.")
    history = payload.get("history", [])
    if not isinstance(history, list) or len(history) > 8:
        raise APIError("history must contain at most 8 recent messages.")
    clean_history = []
    for item in history:
        if not isinstance(item, dict) or set(item) != {"role", "content"}:
            raise APIError("Each history item must contain role and content.")
        if item["role"] not in {"user", "assistant"} or not isinstance(item["content"], str) or len(item["content"]) > 1_200:
            raise APIError("History messages must be short user or assistant messages.")
        clean_history.append({"role": item["role"], "content": item["content"]})
    ticket_id = payload.get("ticket_id")
    if ticket_id is not None and (isinstance(ticket_id, bool) or not isinstance(ticket_id, int) or ticket_id < 1):
        raise APIError("ticket_id must be a positive integer.")
    user = None
    auth = request.headers.get("Authorization", "")
    if auth:
        if not auth.startswith("Bearer "):
            raise APIError("Invalid authorization header.", 401, "authentication_failed")
        try:
            claims = _extensions("token_service").verify(auth[7:])
        except AuthenticationError as error:
            raise APIError(str(error), 401, "authentication_failed") from error
        user = _extensions("ticket_repository").get_user_by_id(claims["id"])
        if not user or user.get("disabled") or user.get("role") not in ROLES:
            raise APIError("You do not have permission to use this action.", 403, "forbidden")
    if ticket_id is not None and user is None:
        raise APIError("Sign in to include ticket information.", 401, "authentication_required")
    try:
        response = _extensions("project_support_bot").answer(
            message,
            history=clean_history,
            repository=_extensions("ticket_repository") if user else None,
            allow_ticket_context=user is not None,
            ticket_id=ticket_id,
        )
    except ValueError as error:
        raise APIError(str(error)) from error
    return {"response": response, "request_id": g.request_id}, 200


@api_blueprint.get("/support/status")
def support_status():
    return {"local_llm": _extensions("local_support_llm").status(), "request_id": g.request_id}, 200


@api_blueprint.get("/demo-info")
def demo_info():
    """Expose local demo login details only in development environments."""
    if settings.environment != "development":
        return {"enabled": False}, 200
    email = current_app.config.get("DEMO_ADMIN_EMAIL")
    password = current_app.config.get("DEMO_ADMIN_PASSWORD")
    if not email or not password:
        return {"enabled": False}, 200
    return {"enabled": True, "email": email, "password": password}, 200


@api_blueprint.get("/ready")
def readiness():
    policy = policy_description()
    model_status = _extensions("candidate_model_service").status()
    origins = {item.get("data_origin") for item in model_status.values() if item.get("available")}
    observed_ready = all(model_status.get(kind, {}).get("available") and model_status[kind].get("data_origin") == "observed" for kind in ("routing", "sla"))
    ml_status = "observed_models_ready" if observed_ready else ("synthetic_candidates_only" if origins else "models_unavailable")
    return {"status": "ready", "sla_policy_version": policy["version"],
            "sla_policy": policy, "ml_status": ml_status, "models": model_status,
            "request_id": g.request_id}, 200


@api_blueprint.get("/models/candidates")
@require_roles("admin", "analyst", "support_agent")
def candidate_model_status():
    return {"models": _extensions("candidate_model_service").status(), "request_id": g.request_id}, 200


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
    payload = _payload()
    allowed = {"summary", "description", "priority", "created_hours", "assigned_team", "status"}
    unknown = set(payload) - allowed
    if unknown:
        raise APIError(f"Unsupported ticket field(s): {', '.join(sorted(unknown))}.")
    ticket = _extensions("ticket_repository").upsert_ticket(_ticket_fields(payload, require_age=False))
    _extensions("ticket_repository").audit(g.current_user["email"], "ticket_created", "ticket", str(ticket["id"]))
    ml_assessment = _store_ml_assessment(ticket)
    return {"ticket": ticket, "ml_assessment": ml_assessment, "request_id": g.request_id}, 201


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
    tickets = [_ticket_with_live_sla({**ticket, "ml_assessment": repository.latest_ml_assessment(ticket["id"])}) for ticket in tickets]
    return {"tickets": tickets, "limit": limit, "offset": offset, "total": repository.ticket_count(priority, status, team, search), "request_id": g.request_id}, 200


@api_blueprint.get("/tickets/<int:ticket_id>")
@require_roles("admin", "analyst", "support_agent")
def get_ticket(ticket_id: int):
    ticket = _extensions("ticket_repository").get_ticket(ticket_id)
    if not ticket: raise APIError("Ticket not found.", 404, "not_found")
    assessment = assess_sla(ticket["priority"], ticket["created_hours"])
    return {"ticket": ticket, "sla_assessment": assessment,
            "ml_assessment": _extensions("ticket_repository").latest_ml_assessment(ticket_id),
            "request_id": g.request_id}, 200


@api_blueprint.get("/sla-policy")
@require_roles("admin", "analyst", "support_agent")
def sla_policy():
    return {"policy": policy_description(), "request_id": g.request_id}, 200


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
    ticket = _extensions("ticket_repository").update_ticket(ticket_id, {key: validated[key] for key in payload})
    _extensions("ticket_repository").audit(g.current_user["email"], "ticket_updated", "ticket", str(ticket_id))
    ml_assessment = _store_ml_assessment(ticket)
    return {"ticket": ticket, "ml_assessment": ml_assessment, "request_id": g.request_id}, 200


@api_blueprint.get("/analytics")
@require_roles("admin", "analyst")
def analytics():
    return {"analytics": _dashboard_sla(_extensions("ticket_repository").analytics()), "request_id": g.request_id}, 200


@api_blueprint.get("/sla/alerts")
@require_roles("admin", "analyst", "support_agent")
def sla_alerts():
    analytics = _dashboard_sla({})
    return {"alerts": analytics["sla_alerts"],
            "breached": analytics["active_breached_tickets"],
            "approaching": analytics["active_approaching_tickets"],
            "request_id": g.request_id}, 200


@api_blueprint.post("/tickets/<int:ticket_id>/predict")
@require_roles("admin", "support_agent")
def predict_ticket(ticket_id: int):
    prediction = _extensions("ticket_service").predict(ticket_id)
    if not prediction: raise APIError("Ticket not found.", 404, "not_found")
    ticket = _extensions("ticket_repository").get_ticket(ticket_id)
    prediction["ml_assessment"] = _store_ml_assessment(ticket)
    _extensions("ticket_repository").audit(g.current_user["email"], "ticket_predicted", "ticket", str(ticket_id))
    return {"prediction": prediction, "request_id": g.request_id}, 201


@api_blueprint.post("/tickets/<int:ticket_id>/experimental-predict")
@require_roles("admin", "support_agent")
def experimental_ticket_prediction(ticket_id: int):
    ticket = _extensions("ticket_repository").get_ticket(ticket_id)
    if not ticket:
        raise APIError("Ticket not found.", 404, "not_found")
    try:
        prediction = _extensions("candidate_model_service").predict(ticket)
    except CandidateArtifactError as error:
        raise APIError(str(error), 503, "candidate_model_unavailable") from error
    except ValueError as error:
        raise APIError(str(error)) from error
    return {"prediction": prediction, "request_id": g.request_id}, 200


@api_blueprint.get("/tickets/<int:ticket_id>/predictions")
@require_roles("admin", "analyst", "support_agent")
def prediction_history(ticket_id: int):
    if not _extensions("ticket_repository").get_ticket(ticket_id): raise APIError("Ticket not found.", 404, "not_found")
    return {"predictions": _extensions("ticket_repository").predictions_for_ticket(ticket_id), "request_id": g.request_id}, 200


@api_blueprint.get("/tickets/<int:ticket_id>/ml-assessments")
@require_roles("admin", "analyst", "support_agent")
def ml_assessment_history(ticket_id: int):
    repository = _extensions("ticket_repository")
    if not repository.get_ticket(ticket_id):
        raise APIError("Ticket not found.", 404, "not_found")
    return {"assessments": repository.ml_assessments_for_ticket(ticket_id), "request_id": g.request_id}, 200


@api_blueprint.post("/tickets/<int:ticket_id>/predictions/<int:prediction_id>/decision")
@require_roles("admin", "support_agent")
def decide_prediction(ticket_id: int, prediction_id: int):
    payload = _payload(); decision = payload.get("decision"); selected_team = payload.get("selected_team"); reason = payload.get("reason")
    if decision not in {"accepted", "overridden"}:
        raise APIError("decision must be accepted or overridden.")
    if selected_team is not None and (not isinstance(selected_team, str) or not selected_team.strip()):
        raise APIError("selected_team must be a non-empty string when supplied.")
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        raise APIError("reason must be a non-empty string when supplied.")
    if decision == "overridden" and (not selected_team or not reason):
        raise APIError("Overrides require selected_team and reason.")
    try:
        feedback = _extensions("ticket_repository").record_prediction_feedback(ticket_id, prediction_id, decision, selected_team, reason, g.current_user["email"])
    except ValueError as error:
        raise APIError(str(error), 409, "decision_already_recorded") from error
    if not feedback:
        raise APIError("Prediction not found for this ticket.", 404, "not_found")
    _extensions("ticket_repository").audit(g.current_user["email"], f"prediction_{decision}", "prediction", str(prediction_id))
    return {"feedback": feedback, "request_id": g.request_id}, 201



@api_blueprint.post("/tickets/<int:ticket_id>/feedback")
@require_roles("admin", "support_agent")
def submit_ticket_feedback(ticket_id: int):
    payload = _payload()
    repository = _extensions("ticket_repository")

    prediction_id = payload.get("prediction_id")
    decision = payload.get("decision")
    comment = payload.get("comment")
    corrected_team = payload.get("corrected_team")

    if type(prediction_id) is not int or prediction_id <= 0:
        raise APIError("prediction_id must be a positive integer.")

    if decision not in {"accept", "override"}:
        raise APIError("decision must be accept or override.")

    if comment is not None and (
        not isinstance(comment, str) or not comment.strip()
    ):
        raise APIError("comment must be a non-empty string.")

    if decision == "override" and (
        not isinstance(corrected_team, str) or not corrected_team.strip()
    ):
        raise APIError("corrected_team is required for an override.")

    if not repository.get_ticket(ticket_id):
        raise APIError("Ticket not found.", 404, "not_found")

    predictions = repository.predictions_for_ticket(ticket_id)
    prediction = next(
        (p for p in predictions if p["id"] == prediction_id),
        None,
    )

    if prediction is None:
        raise APIError("Prediction not found.", 404, "not_found")

    selected_team = (
        prediction["recommended_team"]
        if decision == "accept"
        else corrected_team.strip()
    )

    stored_decision = "accepted" if decision == "accept" else "overridden"

    try:
        feedback = repository.record_prediction_feedback(
            ticket_id,
            prediction_id,
            stored_decision,
            selected_team,
            comment.strip() if comment else None,
            g.current_user["email"],
        )
    except ValueError as error:
        raise APIError(str(error), 409, "decision_already_recorded") from error

    if feedback is None:
        raise APIError("Prediction not found.", 404, "not_found")

    ticket = repository.update_ticket(
        ticket_id, {"assigned_team": selected_team}
    )

    repository.audit(
        g.current_user["email"],
        f"ticket_feedback_{decision}",
        "ticket",
        str(ticket_id),
    )

    feedback["decision"] = decision
    feedback["corrected_team"] = (
        selected_team if decision == "override" else None
    )

    return {
        "feedback": feedback,
        "ticket": ticket,
        "request_id": g.request_id,
    }, 201


@api_blueprint.get("/tickets/<int:ticket_id>/feedback")
@require_roles("admin", "analyst", "support_agent")
def get_ticket_feedback(ticket_id: int):
    repository = _extensions("ticket_repository")

    if not repository.get_ticket(ticket_id):
        raise APIError("Ticket not found.", 404, "not_found")

    history = repository.predictions_for_ticket(ticket_id)
    feedback = []

    for item in history:
        if not item.get("decision"):
            continue

        decision = (
            "accept" if item["decision"] == "accepted" else "override"
        )

        feedback.append({
            "prediction_id": item["id"],
            "decision": decision,
            "corrected_team": (
                item.get("selected_team")
                if decision == "override" else None
            ),
            "comment": item.get("reason"),
            "actor_email": item.get("actor_email"),
            "decided_at": item.get("decided_at"),
        })

    return {
        "feedback": feedback,
        "request_id": g.request_id,
    }, 200


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
