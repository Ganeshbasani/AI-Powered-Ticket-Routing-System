"""Stage 2 human feedback loop tests.

These are intended to run in the project's normal development environment:
pytest -q tests/test_stage2_feedback.py
"""

from __future__ import annotations

from src.api.app import create_app
from src.persistence.database import Database
from src.platform.services import TokenService


def _setup(tmp_path):
    app = create_app(database=Database(tmp_path / "app.db"), token_service=TokenService("test-secret"))
    repo = app.extensions["ticket_repository"]
    admin = repo.create_user("admin@example.com", "password", "admin")
    token = {"Authorization": f"Bearer {app.extensions['token_service'].issue(admin)}"}
    ticket = repo.upsert_ticket({
        "summary": "VPN disconnecting",
        "description": "Users cannot stay connected.",
        "priority": "High",
        "created_hours": 10,
        "issue_type": "Network",
    })
    return app, repo, token, ticket


def test_feedback_accept_applies_predicted_team(tmp_path):
    app, repo, token, ticket = _setup(tmp_path)
    client = app.test_client()
    response = client.post(f"/api/v1/tickets/{ticket['id']}/predict", headers=token)
    assert response.status_code == 201
    prediction = response.get_json()["prediction"]

    feedback = client.post(
        f"/api/v1/tickets/{ticket['id']}/feedback",
        headers=token,
        json={"prediction_id": prediction["id"], "decision": "accept", "comment": "AI route accepted."},
    )
    assert feedback.status_code == 201
    assert feedback.get_json()["ticket"]["assigned_team"] == prediction["recommended_team"]
    assert feedback.get_json()["feedback"]["decision"] == "accept"
    assert repo.analytics()["accept_count"] == 1


def test_feedback_override_applies_corrected_team_and_is_audited(tmp_path):
    app, repo, token, ticket = _setup(tmp_path)
    client = app.test_client()
    prediction = client.post(f"/api/v1/tickets/{ticket['id']}/predict", headers=token).get_json()["prediction"]

    feedback = client.post(
        f"/api/v1/tickets/{ticket['id']}/feedback",
        headers=token,
        json={
            "prediction_id": prediction["id"],
            "decision": "override",
            "corrected_team": "L3-Network",
            "comment": "Specialized customer issue.",
        },
    )
    assert feedback.status_code == 201
    assert feedback.get_json()["ticket"]["assigned_team"] == "L3-Network"

    history = client.get(f"/api/v1/tickets/{ticket['id']}/feedback", headers=token)
    assert history.status_code == 200
    assert history.get_json()["feedback"][0]["corrected_team"] == "L3-Network"
    assert "ticket_feedback_override" in [event["action"] for event in repo.audit_events()]
    assert repo.analytics()["override_count"] == 1


def test_feedback_rejects_override_without_team(tmp_path):
    app, _, token, ticket = _setup(tmp_path)
    client = app.test_client()
    prediction = client.post(f"/api/v1/tickets/{ticket['id']}/predict", headers=token).get_json()["prediction"]
    response = client.post(
        f"/api/v1/tickets/{ticket['id']}/feedback",
        headers=token,
        json={"prediction_id": prediction["id"], "decision": "override"},
    )
    assert response.status_code == 400
