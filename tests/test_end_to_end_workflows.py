"""End-to-end ticket, model, clock, and alert workflows on isolated databases."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pandas as pd

from src.api.app import create_app
from src.data.synthetic import generate_synthetic_dataset
from src.ml.candidate_service import CandidateModelService
from src.ml.verified_training import train_observed_models
from src.persistence.database import Database
from src.platform.services import TokenService


def _client(tmp_path, candidate_model_service=None):
    database = Database(tmp_path / "platform.db")
    app = create_app(
        database=database,
        token_service=TokenService("isolated-test-secret"),
        candidate_model_service=candidate_model_service,
    )
    admin = app.extensions["ticket_repository"].create_user("audit@example.test", "test-password", "admin")
    headers = {"Authorization": f"Bearer {app.extensions['token_service'].issue(admin)}"}
    return app, database, app.test_client(), headers


def test_ticket_creation_persists_ml_recommendation_and_separate_policy_record(tmp_path):
    app, database, client, headers = _client(tmp_path)
    response = client.post("/api/v1/tickets", headers=headers, json={
        "summary": "Checkout API returns intermittent gateway timeouts",
        "description": "Customers cannot complete payments after a release.",
        "priority": "High", "created_hours": 3.5,
    })

    assert response.status_code == 201
    payload = response.get_json()
    ticket = payload["ticket"]
    assessment = payload["ml_assessment"]
    assert ticket["assigned_team"] is None
    assert assessment["status"] in {"experimental", "observed"}
    assert assessment["routing_team"]
    assert assessment["routing_review_required"] in {True, False}
    assert assessment["sla_breach_prediction"] in {"Yes", "No"}
    assert assessment["metadata"]["real_world_performance_claim"] is False
    assert assessment["features"]["created_hours"] == ticket["created_hours"]

    detail = client.get(f"/api/v1/tickets/{ticket['id']}", headers=headers).get_json()
    assert detail["ml_assessment"]["routing_team"] == assessment["routing_team"]
    assert detail["sla_assessment"]["sla_status"] == "Approaching target"
    with database.session() as connection:
        assert connection.execute("SELECT COUNT(*) FROM ml_assessments").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == 0

    policy_response = client.post(f"/api/v1/tickets/{ticket['id']}/predict", headers=headers)
    assert policy_response.status_code == 201
    policy_prediction = policy_response.get_json()["prediction"]
    assert policy_prediction["model_version"] == "priority-age-policy-v2"
    assert policy_prediction["ml_assessment"]["routing_team"] == assessment["routing_team"]
    history = client.get(f"/api/v1/tickets/{ticket['id']}/predictions", headers=headers).get_json()
    assert history["predictions"][0]["prediction_snapshot_id"]


def test_critical_ticket_is_persisted_with_manual_review_reasons(tmp_path):
    _, database, client, headers = _client(tmp_path)
    response = client.post("/api/v1/tickets", headers=headers, json={
        "summary": "Critical production outage affecting all tenants",
        "description": "Payment requests return errors after deploy.",
        "priority": "Critical",
    })

    assert response.status_code == 201
    body = response.get_json()
    assert body["ticket"]["priority"] == "Critical"
    assert body["ticket"]["assigned_team"] is None
    detail = client.get(f"/api/v1/tickets/{body['ticket']['id']}", headers=headers).get_json()
    assert detail["sla_assessment"]["target_hours"] == 1
    assert body["ml_assessment"]["routing_review_required"] is True
    reasons = body["ml_assessment"]["metadata"]["models"]["routing"]["review_reasons"]
    assert any("synthetic data" in reason for reason in reasons)
    assert any("Critical" in reason for reason in reasons)
    with database.session() as connection:
        stored = connection.execute("SELECT priority FROM tickets WHERE id=?", (body["ticket"]["id"],)).fetchone()
        assert stored["priority"] == "Critical"
        assert connection.execute("SELECT COUNT(*) FROM ml_assessments").fetchone()[0] == 1


def test_sla_clock_advances_and_dashboard_alerts_update_from_current_age(tmp_path):
    app, database, client, headers = _client(tmp_path)
    created = client.post("/api/v1/tickets", headers=headers, json={
        "summary": "Payment service degraded", "priority": "High", "created_hours": 1.5,
    }).get_json()["ticket"]
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    with database.session() as connection:
        connection.execute("UPDATE tickets SET age_reference_at=? WHERE id=?", (past, created["id"]))

    detail = client.get(f"/api/v1/tickets/{created['id']}", headers=headers).get_json()
    assert 3.49 <= detail["ticket"]["created_hours"] <= 3.51
    assert detail["sla_assessment"]["sla_status"] == "Approaching target"
    alerts = client.get("/api/v1/sla/alerts", headers=headers).get_json()
    assert alerts["approaching"] == 1
    assert alerts["alerts"][0]["id"] == created["id"]

    dashboard = client.get("/api/v1/analytics", headers=headers).get_json()["analytics"]
    assert dashboard["active_approaching_tickets"] == 1


def test_missing_models_do_not_block_ticket_creation_or_assign_team(tmp_path):
    empty_models = CandidateModelService(tmp_path / "empty-candidates")
    _, database, client, headers = _client(tmp_path, candidate_model_service=empty_models)
    response = client.post("/api/v1/tickets", headers=headers, json={
        "summary": "New ticket with models unavailable", "priority": "Medium",
    })

    assert response.status_code == 201
    assert response.get_json()["ticket"]["assigned_team"] is None
    assert response.get_json()["ml_assessment"]["status"] == "unavailable"
    with database.session() as connection:
        assert connection.execute("SELECT COUNT(*) FROM ml_assessments").fetchone()[0] == 0


def test_ticket_create_rejects_user_supplied_outcomes_and_prediction_fields(tmp_path):
    _, database, client, headers = _client(tmp_path)
    response = client.post("/api/v1/tickets", headers=headers, json={
        "summary": "Never accept caller-authored training labels", "priority": "High",
        "actual_sla_breach": "Yes",
    })
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    with database.session() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0


def test_observed_training_rejects_bundled_legacy_three_row_dataset(tmp_path):
    data = tmp_path / "legacy.csv"
    pd.read_csv("data/tickets.csv").to_csv(data, index=False)
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    manifest = tmp_path / "legacy.manifest.json"
    manifest.write_text(json.dumps({
        "record_origin": "observed", "source_system": "test", "extracted_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": digest, "source_profile": {"configured": True, "name": "unit-test"},
    }), encoding="utf-8")

    try:
        train_observed_models(data, manifest, tmp_path / "verified")
    except ValueError as error:
        assert "missing required provenance fields" in str(error)
    else:
        raise AssertionError("The three-row legacy dataset must not train an observed model.")


def test_observed_model_training_and_inference_use_temporal_fixture_only_in_tmp(tmp_path):
    frame, _ = generate_synthetic_dataset(300, seed=731)
    # This fixture exercises the observed-data contract only; it is never stored
    # as product data or reported as real model evidence.
    frame["ingestion_source"] = "test-fixture-observed"
    data = tmp_path / "fixture.csv"
    frame.to_csv(data, index=False)
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    manifest = tmp_path / "fixture.manifest.json"
    manifest.write_text(json.dumps({
        "record_origin": "observed", "source_system": "unit-test-fixture",
        "extracted_at": datetime.now(UTC).isoformat(), "dataset_sha256": digest,
        "source_profile": {"configured": True, "name": "unit-test-fixture"},
    }), encoding="utf-8")

    trained = train_observed_models(data, manifest, tmp_path / "verified")
    service = CandidateModelService(tmp_path / "candidates")
    status = service.status()
    result = service.predict({"summary": "VPN connection fails during calls", "description": "Connection drops.", "priority": "High", "created_hours": 2})

    assert set(trained) == {"routing", "sla"}
    assert all(item["evaluation"]["data_origin"] == "observed" for item in trained.values())
    assert status["routing"]["model_version"] == "observed-v1"
    assert status["sla"]["model_version"] == "observed-v1"
    assert result["data_origin"] == "observed"
    assert result["metadata"]["real_world_performance_claim"] is False
