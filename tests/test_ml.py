"""Tests for the machine learning data processing and model service."""

from __future__ import annotations

import joblib
import pandas as pd
import pytest

from src.ml.data_processing import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    load_ticket_data,
    prepare_features,
    prepare_labels,
    validate_ticket_data,
)
from src.ml.model import ModelService
from src.config.settings import settings


def test_load_ticket_data():
    df = load_ticket_data(settings.data_path)
    assert isinstance(df, pd.DataFrame)
    assert "priority" in df.columns
    assert "created_hours" in df.columns


def test_prepare_features_and_labels():
    df = load_ticket_data(settings.data_path)
    df = validate_ticket_data(df)
    features = prepare_features(df)
    labels = prepare_labels(df)

    assert "priority" in features.columns
    assert features.shape[0] == labels.shape[0]


def test_feature_schema_excludes_target_and_post_outcome_columns():
    data_frame = load_ticket_data(settings.data_path)
    features = prepare_features(data_frame)

    assert tuple(features.columns) == FEATURE_COLUMNS
    assert TARGET_COLUMN not in features.columns
    assert "assigned_team" not in features.columns
    assert "ticket_id" not in features.columns


def test_validation_removes_duplicates_and_rows_missing_required_values():
    data_frame = pd.DataFrame(
        {
            "priority": ["High", "High", "Medium"],
            "created_hours": [1, 1, None],
            "sla_breach": ["Yes", "Yes", "No"],
        }
    )

    validated = validate_ticket_data(data_frame)

    assert len(validated) == 1
    assert validated.iloc[0]["priority"] == "High"


@pytest.mark.parametrize("created_hours", [-1, float("inf")])
def test_validate_ticket_data_rejects_invalid_created_hours(created_hours):
    data_frame = pd.DataFrame(
        {"priority": ["High"], "created_hours": [created_hours], "sla_breach": ["Yes"]}
    )

    with pytest.raises(ValueError, match="finite, non-negative"):
        validate_ticket_data(data_frame)


def test_model_service_trains_when_artifact_is_missing(tmp_path):
    model_service = ModelService(model_path=tmp_path / "sla_model.joblib")
    model_service.ensure_model()

    assert model_service.model_path.exists()

    artifact = joblib.load(model_service.model_path)
    assert artifact["feature_schema"] == list(FEATURE_COLUMNS)
    assert artifact["target_definition"] == "sla_breach: Yes=1, No=0"
    assert artifact["training_samples"] == 3
    assert artifact["evaluation"]["status"] == "not_available"


def test_model_service_predict_uses_training_feature_names(tmp_path):
    model_service = ModelService(model_path=tmp_path / "sla_model.joblib")
    result = model_service.predict("Medium", 5)

    assert result["assigned_team"] in {"L1", "L2"}
    assert result["sla_breach_risk"] in {"High", "Low"}


def test_fresh_artifact_uses_the_same_pipeline_for_inference(tmp_path):
    model_service = ModelService(model_path=tmp_path / "sla_model.joblib")
    model_service.ensure_model()
    model = model_service.load_model()

    production_input = pd.DataFrame(
        {"priority": ["High"], "created_hours": [5.0]}, columns=FEATURE_COLUMNS
    )
    pipeline_prediction = model.predict(production_input)[0]
    service_prediction = model_service.predict("High", 5.0)["sla_breach_risk"]

    assert service_prediction == ("High" if pipeline_prediction else "Low")


def test_corrupt_artifact_is_rebuilt_before_prediction(tmp_path):
    artifact_path = tmp_path / "sla_model.joblib"
    artifact_path.write_bytes(b"not a joblib artifact")
    model_service = ModelService(model_path=artifact_path)

    result = model_service.predict("Low", 1)

    assert result["sla_breach_risk"] in {"High", "Low"}
    assert joblib.load(artifact_path)["feature_schema"] == list(FEATURE_COLUMNS)


@pytest.mark.parametrize(
    ("priority", "created_hours"),
    [("Critical", 5), ("High", -1), ("Low", float("inf"))],
)
def test_model_service_rejects_invalid_prediction_inputs(priority, created_hours):
    model_service = ModelService()

    with pytest.raises(ValueError):
        model_service.predict(priority, created_hours)
