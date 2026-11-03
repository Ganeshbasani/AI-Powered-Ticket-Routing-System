"""Versioned candidate models trained only through explicit commands."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, confusion_matrix, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.data.contract import validate_prediction_feature_fields
from src.data.nlp import combine_ticket_text
from src.data.pipeline import chronological_split

CANDIDATE_FEATURE_SCHEMA_VERSION = "candidate-v1"
CANDIDATE_MODEL_VERSION = "8c-candidate-3"
STRUCTURED_FEATURES = ("priority", "issue_type", "project", "component", "created_hours")


def train_candidate_models(data_path: Path | str, manifest_path: Path | str, artifact_directory: Path | str) -> dict[str, dict[str, Any]]:
    """Train separate synthetic-development candidates without touching production."""
    frame = pd.read_csv(data_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not manifest.get("synthetic"):
        raise ValueError("Candidate training requires an explicitly synthetic manifest in Phase 8C.")
    if len(frame) < 100:
        raise ValueError("Candidate training requires at least 100 records.")
    train, _, test = chronological_split(frame)
    results = {}
    for name, target in (("routing", "initial_triage_team"), ("sla", "actual_sla_breach")):
        if train[target].nunique() < 2 or test[target].nunique() < 2:
            raise ValueError(f"{name} candidate needs at least two classes in train and test data.")
        pipeline = _pipeline()
        pipeline.fit(_features(train), train[target])
        test_features = _features(test)
        predicted = pipeline.predict(test_features)
        probabilities = pipeline.predict_proba(test_features)
        artifact = _save_artifact(
            Path(artifact_directory) / f"{name}-{CANDIDATE_MODEL_VERSION}.joblib",
            pipeline, name, target, manifest, len(train), _evaluate(test[target], predicted, name, probabilities, pipeline.classes_),
        )
        results[name] = artifact
    return results


def _features(frame: pd.DataFrame) -> pd.DataFrame:
    validate_prediction_feature_fields(STRUCTURED_FEATURES)
    data = frame.loc[:, STRUCTURED_FEATURES].copy()
    data["combined_text"] = [combine_ticket_text(record) for record in frame.to_dict("records")]
    return data


def _pipeline() -> Pipeline:
    preprocess = ColumnTransformer([
        ("structured", OneHotEncoder(handle_unknown="ignore"), ["priority", "issue_type", "project", "component"]),
        ("age", "passthrough", ["created_hours"]),
        ("text", TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=2_000), "combined_text"),
    ])
    return Pipeline([("preprocess", preprocess), ("classifier", LogisticRegression(max_iter=1_000, class_weight="balanced", random_state=42))])


def _evaluate(actual: pd.Series, predicted: Any, name: str, probabilities: Any, classes: Any) -> dict[str, Any]:
    labels = sorted(actual.unique())
    precision, recall, f1, support = precision_recall_fscore_support(actual, predicted, labels=labels, zero_division=0)
    result: dict[str, Any] = {
        "data_origin": "synthetic", "warning": "Synthetic evaluation is pipeline evidence, not production performance.",
        "class_support": {str(label): int(count) for label, count in zip(labels, support)},
        "per_class": {str(label): {"precision": float(p), "recall": float(r), "f1": float(score)} for label, p, r, score in zip(labels, precision, recall, f1)},
        "confusion_matrix": confusion_matrix(actual, predicted, labels=labels).tolist(), "labels": labels,
        "accuracy": float(accuracy_score(actual, predicted)),
    }
    if name == "routing":
        result["macro_f1"] = float(f1.mean())
    else:
        result["precision"] = float(precision.mean()); result["recall"] = float(recall.mean()); result["f1"] = float(f1.mean())
        yes_index = list(classes).index("Yes")
        result["threshold"] = 0.5
        result["brier_score"] = float(brier_score_loss((actual == "Yes").astype(int), probabilities[:, yes_index]))
    return result


def _save_artifact(path: Path, pipeline: Pipeline, kind: str, target: str, manifest: dict[str, Any], samples: int, evaluation: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"Candidate artifact already exists: {path}. Use a new model version or artifact directory.")
    artifact = {
        "kind": kind, "model_version": CANDIDATE_MODEL_VERSION, "feature_schema_version": CANDIDATE_FEATURE_SCHEMA_VERSION,
        "feature_schema": [*STRUCTURED_FEATURES, "combined_text"], "target": target, "training_manifest_checksum": manifest["logical_checksum_sha256"],
        "generator_version": manifest["generator_version"], "rule_set_version": manifest["rule_set_version"], "random_seed": manifest["random_seed"],
        "training_timestamp": datetime.now(UTC).isoformat(), "training_samples": samples, "evaluation": evaluation,
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()}, "pipeline": pipeline,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    joblib.dump(artifact, temporary); temporary.replace(path)
    artifact_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar = path.with_suffix(path.suffix + ".manifest.json")
    sidecar.write_text(json.dumps({k: v for k, v in artifact.items() if k != "pipeline"} | {"artifact_sha256": artifact_sha256}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"artifact_path": str(path), "artifact_sha256": artifact_sha256, "evaluation": evaluation}
