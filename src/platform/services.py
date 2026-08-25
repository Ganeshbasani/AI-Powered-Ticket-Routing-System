"""Authentication, ticket prediction, and mock JIRA ingestion services."""

from __future__ import annotations

from typing import Any
from time import monotonic

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from src.ml.model import ModelService
from src.persistence.repository import TicketRepository

ROLES = {"admin", "analyst", "support_agent"}


class AuthenticationError(ValueError):
    pass


class InMemoryRateLimiter:
    """Per-process fixed-window limiter; distributed deployments need shared storage."""
    def __init__(self, clock=monotonic) -> None:
        self._buckets: dict[tuple[str, str], tuple[float, int]] = {}
        self._clock = clock

    def allow(self, key: str, scope: str, limit: int, window_seconds: int = 60) -> bool:
        now = self._clock(); bucket_key = (key, scope); start, count = self._buckets.get(bucket_key, (now, 0))
        if now - start >= window_seconds: start, count = now, 0
        count += 1; self._buckets[bucket_key] = (start, count)
        return count <= limit


class TokenService:
    def __init__(self, secret: str | None) -> None:
        self.secret = secret

    def issue(self, user: dict[str, Any]) -> str:
        if not self.secret:
            raise AuthenticationError("Authentication is not configured.")
        return URLSafeTimedSerializer(self.secret, salt="sla-ticket-routing").dumps({"id": user["id"], "role": user["role"]})

    def verify(self, token: str, max_age_seconds: int = 3600) -> dict[str, Any]:
        if not self.secret:
            raise AuthenticationError("Authentication is not configured.")
        try:
            return URLSafeTimedSerializer(self.secret, salt="sla-ticket-routing").loads(token, max_age=max_age_seconds)
        except (BadSignature, SignatureExpired) as error:
            raise AuthenticationError("Invalid or expired access token.") from error


class TicketService:
    def __init__(self, repository: TicketRepository, model_service: ModelService) -> None:
        self.repository = repository
        self.model_service = model_service

    def predict(self, ticket_id: int) -> dict[str, Any] | None:
        ticket = self.repository.get_ticket(ticket_id)
        if not ticket:
            return None
        prediction = self.model_service.predict(ticket["priority"], ticket["created_hours"])
        return self.repository.add_prediction(ticket_id, prediction)


class MockJiraProvider:
    """Maps a supplied Jira-like issue payload for local demos and tests."""

    def map_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(issue, dict):
            raise ValueError("JIRA issue must be a JSON object.")
        fields = issue.get("fields")
        if not isinstance(fields, dict) or not isinstance(issue.get("key"), str):
            raise ValueError("JIRA issue must include key and fields.")
        priority = fields.get("priority")
        priority = priority.get("name") if isinstance(priority, dict) else priority
        return {
            "jira_issue_key": issue["key"], "summary": fields.get("summary"), "description": fields.get("description"),
            "priority": priority, "created_hours": fields.get("created_hours"), "status": (fields.get("status") or {}).get("name", "open") if isinstance(fields.get("status"), dict) else "open",
            "source": "jira_mock",
        }
