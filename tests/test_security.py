"""Dedicated Phase 6 authentication, administration, and API-security tests."""

from __future__ import annotations

import pytest
from src.api.app import create_app
from src.cli import bootstrap_admin
from src.persistence.database import Database
from src.platform.services import AuthenticationError, InMemoryRateLimiter, TokenService


def _setup(tmp_path, limits=None):
    app = create_app(database=Database(tmp_path / "app.db"), token_service=TokenService("test-secret"), rate_limiter=InMemoryRateLimiter(), rate_limits=limits)
    repo = app.extensions["ticket_repository"]; admin = repo.create_user("admin@example.com", "password", "admin"); analyst = repo.create_user("analyst@example.com", "password", "analyst")
    token = lambda user: {"Authorization": f"Bearer {app.extensions['token_service'].issue(user)}"}
    return app, repo, token(admin), token(analyst)


def test_login_disabled_token_rbac_and_audit(tmp_path):
    app, repo, admin, analyst = _setup(tmp_path); client = app.test_client()
    assert client.post("/api/v1/auth/login", json={"email": "analyst@example.com", "password": "password"}).status_code == 200
    assert client.get("/api/v1/users", headers=analyst).status_code == 403
    created = client.post("/api/v1/users", headers=admin, json={"email": "agent@example.com", "password": "password123", "role": "support_agent"})
    assert created.status_code == 201 and "password_hash" not in str(created.get_json())
    analyst_id = repo.get_user_by_email("analyst@example.com")["id"]
    assert client.patch(f"/api/v1/users/{analyst_id}", headers=admin, json={"disabled": True}).status_code == 200
    assert client.get("/api/v1/tickets", headers=analyst).status_code == 403
    assert client.post("/api/v1/auth/login", json={"email": "analyst@example.com", "password": "password"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "unknown@example.com", "password": "x"}).status_code == 401
    actions = [event["action"] for event in repo.audit_events()]
    assert {"login", "login_failed", "user_created", "user_disabled"}.issubset(actions)


def test_invalid_token_limits_size_headers_and_bootstrap(tmp_path):
    app, repo, admin, _ = _setup(tmp_path, {"login": 1, "prediction": 1, "jira_import": 1}); client = app.test_client()
    assert client.get("/api/v1/tickets", headers={"Authorization": "Bearer malformed"}).status_code == 401
    assert client.post("/api/v1/predict", json={"priority": "High", "created_hours": 1}).status_code == 200
    assert client.post("/api/v1/predict", json={"priority": "High", "created_hours": 1}).status_code == 429
    health = client.get("/api/v1/health"); assert health.status_code == 200 and health.headers["X-Content-Type-Options"] == "nosniff" and health.headers["Cache-Control"] == "no-store"
    oversized = client.post("/api/v1/tickets", headers=admin, data="x" * (1024 * 1024 + 1), content_type="application/json")
    assert oversized.status_code == 413 and "traceback" not in oversized.get_data(as_text=True).lower()
    database = Database(tmp_path / "bootstrap.db")
    assert bootstrap_admin("root@example.com", "password123", database) == "Administrator created."
    with pytest.raises(ValueError, match="administrator already exists"):
        bootstrap_admin("other@example.com", "password123", database)
    with database.session() as connection:
        assert connection.execute("SELECT password_hash FROM users").fetchone()[0] != "password123"


def test_expired_token_and_missing_bootstrap_configuration(tmp_path):
    token_service = TokenService("test-secret")
    token = token_service.issue({"id": 1, "role": "admin"})
    with pytest.raises(AuthenticationError):
        token_service.verify(token, max_age_seconds=-1)
    with pytest.raises(ValueError, match="required"):
        bootstrap_admin(database=Database(tmp_path / "missing.db"))


def test_login_and_jira_limits_are_independent_and_reset(tmp_path):
    app, _, admin, _ = _setup(tmp_path, {"login": 1, "prediction": 5, "jira_import": 1}); client = app.test_client()
    assert client.post("/api/v1/auth/login", json={"email": "bad@example.com", "password": "bad"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "bad@example.com", "password": "bad"}).status_code == 429
    issue = {"key": "SEC-1", "fields": {"summary": "Test", "priority": {"name": "High"}, "created_hours": 1}}
    assert client.post("/api/v1/integrations/jira/import", headers=admin, json={"issue": issue}).status_code == 200
    assert client.post("/api/v1/integrations/jira/import", headers=admin, json={"issue": issue}).status_code == 429
    clock = [0.0]; limiter = InMemoryRateLimiter(lambda: clock[0])
    assert limiter.allow("client", "scope", 1) and not limiter.allow("client", "scope", 1)
    clock[0] = 61.0
    assert limiter.allow("client", "scope", 1)
