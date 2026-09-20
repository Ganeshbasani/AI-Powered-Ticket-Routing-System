"""Tests for ticket triage data processing and model service."""

from __future__ import annotations

import joblib
import pandas as pd
import pytest

from src.ml.data_processing import FEATURE_COLUMNS, load_ticket_data, prepare_features, validate_ticket_data
from src.ml.model import ModelService


def test_load_ticket_data():
    df = load_ticket_data("data/tickets.csv")
    assert isinstance(df, pd.DataFrame)
    assert {"summary", "description", "priority", "issue_type", "final_team", "sla_breach"}.issubset(df.columns)
    assert len(df) >= 1000


def test_prepare_features_and_validation():
    df = validate_ticket_data(load_ticket_data("data/tickets.csv"))
    features = prepare_features(df)
    assert tuple(features.columns) == FEATURE_COLUMNS
    assert "sla_breach" not in features.columns
    assert "final_team" not in features.columns
    assert "ticket_id" not in features.columns


def test_validation_removes_duplicates_and_rows_missing_required_values():
    data_frame = pd.DataFrame(
        {
            "summary": ["VPN", "VPN", "Checkout"],
            "description": ["down", "down", "error"],
            "priority": ["High", "High", "Medium"],
            "issue_type": ["Network", "Network", "Application"],
            "project": ["Platform", "Platform", "Portal"],
            "component": ["VPN", "VPN", "API"],
            "customer_tier": ["Business", "Business", "Standard"],
            "channel": ["Portal", "Portal", "Email"],
            "created_hours": [1, 1, None],
            "final_team": ["L2-Network", "L2-Network", "L2-Application"],
            "sla_breach": ["Yes", "Yes", "No"],
        }
    )
    validated = validate_ticket_data(data_frame)
    assert len(validated) == 1


@pytest.mark.parametrize("created_hours", [-1, float("inf")])
def test_validate_ticket_data_rejects_invalid_created_hours(created_hours):
    data_frame = pd.DataFrame(
        {
            "summary": ["VPN"], "description": ["down"], "priority": ["High"],
            "issue_type": ["Network"], "project": ["Platform"], "component": ["VPN"],
            "customer_tier": ["Business"], "channel": ["Portal"], "created_hours": [created_hours],
            "final_team": ["L2-Network"], "sla_breach": ["Yes"],
        }
    )
    with pytest.raises(ValueError, match="finite, non-negative"):
        validate_ticket_data(data_frame)


def test_model_service_trains_and_evaluates(tmp_path):
    service = ModelService(model_path=tmp_path / "ticket_triage_models.joblib")
    service.ensure_model()
    assert service.model_path.exists()
    artifact = joblib.load(service.model_path)
    assert artifact["artifact_version"] == 2
    assert artifact["feature_schema"] == list(FEATURE_COLUMNS)
    assert artifact["training_samples"] == 1500
    assert artifact["evaluation"]["status"] == "evaluated"
    assert artifact["evaluation"]["routing"]["f1"] >= 0.70
    assert artifact["evaluation"]["sla"]["f1"] >= 0.70


def test_model_service_prediction_includes_routing_and_sla(tmp_path):
    service = ModelService(model_path=tmp_path / "ticket_triage_models.joblib")
    result = service.predict(
        summary="VPN connection keeps dropping",
        description="Users cannot stay connected to the corporate network.",
        priority="High",
        created_hours=10,
        issue_type="Network",
    )
    assert result["assigned_team"] == result["recommended_team"]
    assert result["assigned_team"] in {"L2-Network", "L2-Application", "L3-Database", "Security", "L1-Hardware", "L1-General"}
    assert result["sla_breach_risk"] in {"High", "Low"}
    assert 0 <= result["sla_probability"] <= 1
    assert 0 <= result["routing_confidence"] <= 1
    assert result["feature_schema"] == list(FEATURE_COLUMNS)


@pytest.mark.parametrize("created_hours", [-1, float("inf")])
def test_model_service_rejects_invalid_prediction_inputs(tmp_path, created_hours):
    service = ModelService(model_path=tmp_path / "ticket_triage_models.joblib")
    with pytest.raises(ValueError):
        service.predict(
            summary="Test ticket", description="Issue", priority="High", created_hours=created_hours
        )


def test_model_service_rejects_invalid_priority(tmp_path):
    service = ModelService(model_path=tmp_path / "ticket_triage_models.joblib")
    with pytest.raises(ValueError):
        service.predict(summary="Test", description="Issue", priority="Critical", created_hours=1)
