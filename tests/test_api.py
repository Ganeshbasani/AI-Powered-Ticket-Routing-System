"""Tests for the hardened SLA prediction API contract."""

from __future__ import annotations

import pytest

from src.api.app import create_app
from src.persistence.database import Database


def _client(tmp_path, **kwargs):
    return create_app(database=Database(tmp_path / "api.db"), **kwargs).test_client()


def _assert_error(response, code: str, status_code: int = 400) -> None:
    payload = response.get_json()
    assert response.status_code == status_code
    assert payload["error"]["code"] == code
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


def test_health_endpoint_has_request_id(tmp_path):
    response = _client(tmp_path).get("/api/v1/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert response.get_json()["request_id"] == response.headers["X-Request-ID"]


def test_readiness_reports_policy_and_model_provenance_without_training(tmp_path):
    response = _client(tmp_path).get("/api/v1/ready")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["sla_policy"]["is_ml_model"] is False
    assert payload["ml_status"] in {"synthetic_candidates_only", "models_unavailable", "observed_models_ready"}


def test_predict_endpoint_success_returns_explained_policy_assessment(tmp_path):
    response = _client(tmp_path).post(
        "/api/v1/predict", json={"priority": "High", "created_hours": 10}
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["sla_status"] == "Breached"
    assert payload["sla_breach_risk"] == "High"
    assert payload["model_version"] == "priority-age-policy-v2"
    assert payload["assigned_team"] == "Unassigned"
    assert payload["explanation"]
    assert payload["request_id"] == response.headers["X-Request-ID"]


def test_critical_priority_is_supported_by_sla_policy(tmp_path):
    client = _client(tmp_path)
    approaching = client.post(
        "/api/v1/predict", json={"priority": "Critical", "created_hours": 0.8}
    )
    breached = client.post(
        "/api/v1/predict", json={"priority": "Critical", "created_hours": 1}
    )

    assert approaching.status_code == 200
    assert approaching.get_json()["target_hours"] == 1
    assert approaching.get_json()["sla_status"] == "Approaching target"
    assert breached.status_code == 200
    assert breached.get_json()["sla_status"] == "Breached"


def test_frontend_is_served_without_a_prior_build_and_has_security_headers(tmp_path):
    client = _client(tmp_path)
    response = client.get("/")

    assert response.status_code == 200
    assert "Ticket Routing Intelligence" in response.get_data(as_text=True)
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"priority": "Urgent", "created_hours": 2},
        {"priority": "High", "created_hours": -1},
        {"priority": "High", "created_hours": "NaN"},
        {"priority": "High", "created_hours": True},
        {"priority": "High", "created_hours": 1, "extra": "not accepted"},
    ],
)
def test_predict_endpoint_rejects_invalid_payloads(payload, tmp_path):
    response = _client(tmp_path).post("/api/v1/predict", json=payload)

    _assert_error(response, "validation_error")


def test_predict_endpoint_rejects_malformed_json(tmp_path):
    response = _client(tmp_path).post(
        "/api/v1/predict", data="{", content_type="application/json"
    )

    _assert_error(response, "validation_error")


def test_unexpected_error_does_not_expose_internal_details(tmp_path):
    class FailingService:
        def predict(self, priority: str, created_hours: float) -> dict:
            raise RuntimeError("internal artifact path: C:/private/model.joblib")

        def readiness(self) -> tuple[bool, str]:
            return False, "invalid"

    response = _client(tmp_path, model_service=FailingService()).post(
        "/api/v1/predict", json={"priority": "High", "created_hours": 1}
    )

    _assert_error(response, "internal_error", 500)
    assert "private" not in response.get_data(as_text=True)
