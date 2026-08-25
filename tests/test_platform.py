"""Integration tests for persistence, access control, and mock JIRA ingestion."""

from __future__ import annotations

from src.api.app import create_app
from src.persistence.database import Database
from src.platform.services import TokenService


def _app(tmp_path):
    app = create_app(database=Database(tmp_path / "platform.db"), token_service=TokenService("test-secret"))
    repository = app.extensions["ticket_repository"]
    admin = repository.create_user("admin@example.com", "password", "admin")
    agent = repository.create_user("agent@example.com", "password", "support_agent")
    return app, {"admin": {"Authorization": f"Bearer {app.extensions['token_service'].issue(admin)}"}, "agent": {"Authorization": f"Bearer {app.extensions['token_service'].issue(agent)}"}}


def test_ticket_prediction_history_and_rbac(tmp_path):
    app, headers = _app(tmp_path); client = app.test_client()
    denied = client.post("/api/v1/tickets", json={"summary": "VPN", "priority": "High", "created_hours": 1})
    assert denied.status_code == 401
    created = client.post("/api/v1/tickets", headers=headers["agent"], json={"summary": "VPN", "priority": "High", "created_hours": 1})
    assert created.status_code == 201
    ticket_id = created.get_json()["ticket"]["id"]
    updated = client.patch(f"/api/v1/tickets/{ticket_id}", headers=headers["agent"], json={"status": "In Progress", "assigned_team": "Network"})
    assert updated.status_code == 200 and updated.get_json()["ticket"]["status"] == "In Progress"
    assert client.post(f"/api/v1/tickets/{ticket_id}/predict", headers=headers["agent"]).status_code == 201
    history = client.get(f"/api/v1/tickets/{ticket_id}/predictions", headers=headers["agent"])
    assert len(history.get_json()["predictions"]) == 1


def test_mock_jira_import_is_idempotent_and_admin_only(tmp_path):
    app, headers = _app(tmp_path); client = app.test_client()
    issue = {"key": "SUP-12", "fields": {"summary": "VPN outage", "priority": {"name": "High"}, "created_hours": 2, "status": {"name": "Open"}}}
    assert client.post("/api/v1/integrations/jira/import", headers=headers["agent"], json={"issue": issue}).status_code == 403
    first = client.post("/api/v1/integrations/jira/import", headers=headers["admin"], json={"issue": issue})
    issue["fields"]["summary"] = "Updated VPN outage"
    second = client.post("/api/v1/integrations/jira/import", headers=headers["admin"], json={"issue": issue})
    assert first.status_code == second.status_code == 200
    assert first.get_json()["ticket"]["id"] == second.get_json()["ticket"]["id"]
    tickets = client.get("/api/v1/tickets?priority=High", headers=headers["admin"]).get_json()["tickets"]
    assert len(tickets) == 1 and tickets[0]["summary"] == "Updated VPN outage"


def test_ticket_search_filters_and_pagination_are_database_backed(tmp_path):
    app, headers = _app(tmp_path); client = app.test_client()
    for summary, priority, status, team in [("VPN issue", "High", "Open", "Network"), ("Email issue", "Low", "Closed", "Messaging")]:
        response = client.post("/api/v1/tickets", headers=headers["agent"], json={"summary": summary, "priority": priority, "created_hours": 1, "status": status, "assigned_team": team})
        assert response.status_code == 201
    response = client.get("/api/v1/tickets?search=VPN&status=Open&team=Network&limit=1&offset=0", headers=headers["agent"])
    payload = response.get_json()
    assert payload["total"] == 1 and payload["tickets"][0]["summary"] == "VPN issue"


def test_mock_jira_import_rejects_malformed_issue_safely(tmp_path):
    app, headers = _app(tmp_path)
    response = app.test_client().post("/api/v1/integrations/jira/import", headers=headers["admin"], json={"issue": "invalid"})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
