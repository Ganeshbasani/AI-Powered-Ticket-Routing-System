"""Train deployable candidates only from provenance-attested observed history."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.data.contract import validate_prediction_feature_fields
from src.data.pipeline import chronological_split, validate
from src.ml.candidates import (
    CANDIDATE_FEATURE_SCHEMA_VERSION,
    STRUCTURED_FEATURES,
    _evaluate,
    _features,
    _pipeline,
)

OBSERVED_MODEL_VERSION = "observed-v1"
MIN_OBSERVED_ROWS = 200
MIN_TRAIN_CLASS_SUPPORT = 10
MIN_TEST_CLASS_SUPPORT = 5
MIN_HOLDOUT_F1 = 0.5
REQUIRED_OBSERVED_FIELDS = (
    "summary", "description", "created_timestamp", "prediction_timestamp", "initial_triage_team",
    "initial_triage_event_id", "initial_triage_decided_at",
    "initial_triage_decision_source", "actual_sla_breach", "sla_outcome_state",
    "sla_policy_id", "sla_policy_version", "sla_source_event_id",
    "sla_outcome_observed_at", "sla_pause_seconds", "sla_extension_seconds",
)


def _parse_time(value: object) -> pd.Timestamp | None:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp) or stamp.tzinfo is None:
        return None
    return stamp.tz_convert("UTC")


def _validate_observed_dataset(frame: pd.DataFrame, manifest: dict[str, Any], dataset_sha256: str) -> None:
    missing = sorted(set(REQUIRED_OBSERVED_FIELDS) - set(frame.columns))
    if missing:
        raise ValueError(f"Observed training data is missing required provenance fields: {', '.join(missing)}.")
    profile = manifest.get("source_profile")
    extracted_at = _parse_time(manifest.get("extracted_at"))
    if manifest.get("record_origin") != "observed" or not isinstance(profile, dict) or profile.get("configured") is not True:
        raise ValueError("Training requires an observed-data manifest with an explicitly configured source_profile.")
    if not str(manifest.get("source_system", "")).strip() or extracted_at is None:
        raise ValueError("The manifest must name the source system and provide a timezone-aware extraction timestamp.")
    if manifest.get("dataset_sha256") != dataset_sha256:
        raise ValueError("The manifest dataset_sha256 does not match the input dataset.")
    if len(frame) < MIN_OBSERVED_ROWS:
        raise ValueError(f"Only {len(frame)} observed rows are available; at least {MIN_OBSERVED_ROWS} are required for a temporal evaluation.")
    validation = validate(frame)
    if not validation.valid:
        raise ValueError("Observed training data failed validation: " + " ".join(validation.errors))
    if validation.duplicate_rows:
        raise ValueError("Observed training data contains exact duplicate rows.")
    for field in ("created_timestamp", "prediction_timestamp", "initial_triage_decided_at"):
        if frame[field].map(_parse_time).isna().any():
            raise ValueError(f"Every observed row requires a valid {field} timestamp.")
    if frame["sla_outcome_observed_at"].map(_parse_time).isna().any():
        raise ValueError("Every SLA label requires a valid sla_outcome_observed_at timestamp.")
    if (frame["sla_outcome_state"].astype(str).str.lower() != "observed").any():
        raise ValueError("Synthetic, unknown, or censored SLA outcomes cannot be used as observed labels.")
    if "ingestion_source" in frame and frame["ingestion_source"].fillna("").astype(str).str.contains("synthetic", case=False).any():
        raise ValueError("Synthetic pipeline rows cannot be promoted to observed training data.")
    if ((frame["summary"].fillna("").astype(str).str.strip() + frame["description"].fillna("").astype(str).str.strip()).eq("")).any():
        raise ValueError("Every observed ticket needs non-empty prediction-time text.")
    created = frame["created_timestamp"].map(_parse_time)
    scored = frame["prediction_timestamp"].map(_parse_time)
    triaged = frame["initial_triage_decided_at"].map(_parse_time)
    outcomes = frame["sla_outcome_observed_at"].map(_parse_time)
    if ((scored < created) | (triaged < created) | (triaged > scored)).any():
        raise ValueError("Prediction and initial-triage timestamps must follow ticket creation and precede/align with scoring.")
    if (outcomes <= scored).any():
        raise ValueError("SLA outcomes must be observed after the recorded prediction timestamp.")
    recorded_age = pd.to_numeric(frame["created_hours"], errors="coerce")
    timestamp_age = (scored - created).dt.total_seconds() / 3600
    if recorded_age.isna().any() or ((recorded_age - timestamp_age).abs() > 0.25).any():
        raise ValueError("created_hours must agree with created_timestamp and prediction_timestamp within 15 minutes.")
    for field in (
        "initial_triage_team", "initial_triage_event_id", "initial_triage_decided_at",
        "initial_triage_decision_source", "sla_policy_id", "sla_policy_version",
        "sla_source_event_id",
    ):
        if frame[field].isna().any() or frame[field].astype(str).str.strip().eq("").any():
            raise ValueError(f"Observed target provenance is incomplete in {field}.")
    if frame["actual_sla_breach"].isna().any() or not set(frame["actual_sla_breach"].dropna()).issubset({"Yes", "No"}):
        raise ValueError("Observed SLA target labels must all be Yes or No.")
    if not set(frame["initial_triage_decision_source"].dropna()).issubset({"human", "automation", "hybrid"}):
        raise ValueError("Routing target provenance must identify a human, automation, or hybrid decision source.")
    for field in ("sla_pause_seconds", "sla_extension_seconds"):
        values = pd.to_numeric(frame[field], errors="coerce")
        if values.isna().any() or (values != 0).any():
            raise ValueError("The current model schema cannot safely train on paused or extended SLA clocks.")
    for field in ("initial_triage_team", "actual_sla_breach"):
        if frame[field].nunique() < 2:
            raise ValueError(f"Observed target {field} must contain at least two classes.")
    validate_prediction_feature_fields((*STRUCTURED_FEATURES, "combined_text"))


def train_observed_models(
    data_path: Path | str,
    manifest_path: Path | str,
    artifact_directory: Path | str = "ml_model/verified",
) -> dict[str, dict[str, Any]]:
    """Train and evaluate routing/SLA models on observed, provenance-attested rows.

    The final 15% by prediction timestamp is held out for SLA reporting. This is
    offline evidence only; deployment suitability still requires owner review.
    """
    data_path, manifest_path = Path(data_path), Path(manifest_path)
    data_bytes = data_path.read_bytes()
    data_sha256 = hashlib.sha256(data_bytes).hexdigest()
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    frame = pd.read_csv(data_path)
    _validate_observed_dataset(frame, manifest, data_sha256)
    route_train, route_validation, route_test = chronological_split(frame, "created_timestamp", train_fraction=0.7, validation_fraction=0.15)
    sla_ordered = frame.assign(_prediction_time=pd.to_datetime(frame["prediction_timestamp"], utc=True, errors="raise")).sort_values("_prediction_time").drop(columns="_prediction_time")
    train_end, validation_end = int(len(sla_ordered) * 0.7), int(len(sla_ordered) * 0.85)
    sla_validation = sla_ordered.iloc[train_end:validation_end]
    sla_test = sla_ordered.iloc[validation_end:]
    if sla_test.empty:
        raise ValueError("The chronological SLA holdout is empty.")
    test_start = pd.to_datetime(sla_test["prediction_timestamp"], utc=True).min()
    sla_train = sla_ordered.iloc[:train_end].loc[
        pd.to_datetime(sla_ordered.iloc[:train_end]["sla_outcome_observed_at"], utc=True) < test_start
    ]
    splits = {
        "routing": (route_train, route_validation, route_test, "initial_triage_team"),
        "sla": (sla_train, sla_validation, sla_test, "actual_sla_breach"),
    }
    targets = {"routing": "initial_triage_team", "sla": "actual_sla_breach"}
    for name, target in targets.items():
        train, validation, test, _ = splits[name]
        if train[target].nunique() < 2 or test[target].nunique() < 2:
            raise ValueError(f"The chronological {name} split must contain every target class in both train and test data.")
        test_counts = test[target].value_counts()
        if (test_counts < MIN_TEST_CLASS_SUPPORT).any():
            raise ValueError(f"The chronological {name} test split needs at least {MIN_TEST_CLASS_SUPPORT} examples of each class.")
        train_counts = train[target].value_counts()
        if (train_counts < MIN_TRAIN_CLASS_SUPPORT).any():
            raise ValueError(f"The chronological {name} training split needs at least {MIN_TRAIN_CLASS_SUPPORT} examples of each class.")

    artifact_directory = Path(artifact_directory)
    planned_paths = [artifact_directory / f"{name}-{OBSERVED_MODEL_VERSION}.joblib" for name in targets]
    if any(path.exists() or path.with_suffix(path.suffix + ".manifest.json").exists() for path in planned_paths):
        raise ValueError("Observed model artifacts already exist; choose a new artifact directory or version.")

    trained: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Any, dict[str, Any]]] = {}
    for name, target in targets.items():
        train, validation, test, _ = splits[name]
        model = _pipeline()
        model.fit(_features(train), train[target])
        test_features = _features(test)
        predicted = model.predict(test_features)
        probabilities = model.predict_proba(test_features)
        evaluation = _evaluate(test[target], predicted, name, probabilities, model.classes_)
        evaluation["data_origin"] = "observed"
        evaluation["warning"] = "Chronological holdout from provenance-attested observed records; this does not guarantee future performance."
        score = evaluation.get("macro_f1") if name == "routing" else evaluation.get("f1")
        if score is None or score < MIN_HOLDOUT_F1:
            raise ValueError(f"The observed {name} model failed the minimum chronological holdout F1 gate ({MIN_HOLDOUT_F1:.2f}); no artifact was written.")
        trained[name] = (train, validation, test, model, evaluation)

    from joblib import dump

    results: dict[str, dict[str, Any]] = {}
    for name, target in targets.items():
        train, validation, test, model, evaluation = trained[name]
        artifact_path = artifact_directory / f"{name}-{OBSERVED_MODEL_VERSION}.joblib"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "kind": name,
            "model_version": OBSERVED_MODEL_VERSION,
            "feature_schema_version": CANDIDATE_FEATURE_SCHEMA_VERSION,
            "feature_schema": [*STRUCTURED_FEATURES, "combined_text"],
            "target": target,
            "data_origin": "observed",
            "source_system": manifest["source_system"],
            "source_profile": manifest["source_profile"],
            "dataset_sha256": data_sha256,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "training_samples": len(train),
            "validation_samples": len(validation),
            "test_samples": len(test),
            "training_timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
            "evaluation": evaluation,
            "pipeline": model,
        }
        temporary_path = artifact_path.with_suffix(artifact_path.suffix + ".tmp")
        try:
            dump(artifact, temporary_path)
            temporary_path.replace(artifact_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        sidecar = artifact_path.with_suffix(artifact_path.suffix + ".manifest.json")
        sidecar.write_text(json.dumps({key: value for key, value in artifact.items() if key != "pipeline"} | {"artifact_sha256": artifact_hash}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        results[name] = {"artifact_path": str(artifact_path), "artifact_sha256": artifact_hash, "evaluation": evaluation}
    return results
