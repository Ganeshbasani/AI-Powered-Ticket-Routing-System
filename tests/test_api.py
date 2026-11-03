"""Tests for the hardened SLA prediction API contract."""

from __future__ import annotations

import pytest

from src.api.app import create_app


def _assert_error(response, code: str, status_code: int = 400) -> None:
    payload = response.get_json()
    assert response.status_code == status_code
    assert payload["error"]["code"] == code
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


def test_health_endpoint_has_request_id():
    response = create_app().test_client().get("/api/v1/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    assert response.get_json()["request_id"] == response.headers["X-Request-ID"]


def test_readiness_reports_missing_artifact_without_training(tmp_path):
    from src.ml.model import ModelService

    service = ModelService(model_path=tmp_path / "missing.joblib")
    response = create_app(model_service=service).test_client().get("/api/v1/ready")

    assert response.status_code == 503
    assert response.get_json()["status"] == "not_ready"
    assert not service.model_path.exists()


def test_predict_endpoint_success_matches_contract():
    response = create_app().test_client().post(
        "/api/v1/predict", json={"priority": "High", "created_hours": 10}
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert set(payload) == {"assigned_team", "sla_breach_risk", "model_version", "request_id"}
    assert payload["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"priority": "Critical", "created_hours": 2},
        {"priority": "High", "created_hours": -1},
        {"priority": "High", "created_hours": "NaN"},
        {"priority": "High", "created_hours": True},
        {"priority": "High", "created_hours": 1, "extra": "not accepted"},
    ],
)
def test_predict_endpoint_rejects_invalid_payloads(payload):
    response = create_app().test_client().post("/api/v1/predict", json=payload)

    _assert_error(response, "validation_error")


def test_predict_endpoint_rejects_malformed_json():
    response = create_app().test_client().post(
        "/api/v1/predict", data="{", content_type="application/json"
    )

    _assert_error(response, "validation_error")


def test_unexpected_error_does_not_expose_internal_details():
    class FailingService:
        def predict(self, priority: str, created_hours: float) -> dict:
            raise RuntimeError("internal artifact path: C:/private/model.joblib")

        def readiness(self) -> tuple[bool, str]:
            return False, "invalid"

    response = create_app(model_service=FailingService()).test_client().post(
        "/api/v1/predict", json={"priority": "High", "created_hours": 1}
    )

    _assert_error(response, "internal_error", 500)
    assert "private" not in response.get_data(as_text=True)
