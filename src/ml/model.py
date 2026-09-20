"""Training, evaluation, artifact validation, and inference for ticket triage."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from threading import RLock
from typing import Any

import joblib
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.config.settings import settings
from src.ml.data_processing import (
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    NUMERIC_COLUMNS,
    ROUTING_TARGET,
    SLA_TARGET,
    TEXT_COLUMNS,
    load_ticket_data,
    prepare_features,
    prepare_routing_labels,
    prepare_sla_labels,
    validate_ticket_data,
)

ARTIFACT_VERSION = 2
MODEL_VERSION = "triage-v1.0"
logger = logging.getLogger("sla_prediction.model")


class ModelArtifactError(ValueError):
    """Raised when a saved model artifact cannot be safely used."""


def _combine_text(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["ticket_text"] = (result["summary"].fillna("") + " " + result["description"].fillna("")).str.strip()
    return result


def _build_preprocessor() -> ColumnTransformer:
    # Text is deliberately included for routing; metadata provides useful context
    # for both routing and SLA prediction.
    return ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=6000), "ticket_text"),
            ("category", OneHotEncoder(handle_unknown="ignore"), list(CATEGORICAL_COLUMNS)),
            ("numeric", StandardScaler(), list(NUMERIC_COLUMNS)),
        ],
        remainder="drop",
    )


def build_routing_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("prepare_text", _TextPreparation()),
            ("preprocess", _build_preprocessor()),
            ("classifier", LogisticRegression(max_iter=2500, class_weight="balanced")),
        ]
    )


def build_sla_pipeline() -> Pipeline:
    return Pipeline(
        steps=[
            ("prepare_text", _TextPreparation()),
            ("preprocess", _build_preprocessor()),
            ("classifier", LogisticRegression(max_iter=2500, class_weight="balanced", random_state=42)),
        ]
    )


class _TextPreparation(BaseEstimator, TransformerMixin):
    """Small sklearn-compatible transformer that adds the combined ticket text."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return _combine_text(X)

    def get_feature_names_out(self, input_features=None):
        if input_features is None:
            return pd.Index(["ticket_text", *FEATURE_COLUMNS], dtype=object)
        return pd.Index(input_features, dtype=object)


def _metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, average="weighted", zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, average="weighted", zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, average="weighted", zero_division=0)), 4),
    }


def train_models(data_frame: pd.DataFrame, test_size: float = 0.2, random_state: int = 42) -> tuple[dict[str, Pipeline], dict[str, Any]]:
    features = _combine_text(prepare_features(data_frame))
    routing_labels = prepare_routing_labels(data_frame)
    sla_labels = prepare_sla_labels(data_frame)

    route_x_train, route_x_test, route_y_train, route_y_test = train_test_split(
        features, routing_labels, test_size=test_size, random_state=random_state, stratify=routing_labels
    )
    sla_x_train, sla_x_test, sla_y_train, sla_y_test = train_test_split(
        features, sla_labels, test_size=test_size, random_state=random_state, stratify=sla_labels
    )

    routing_model = build_routing_pipeline()
    sla_model = build_sla_pipeline()
    routing_model.fit(route_x_train, route_y_train)
    sla_model.fit(sla_x_train, sla_y_train)

    evaluation = {
        "status": "evaluated",
        "dataset_type": "synthetic_development_data",
        "test_size": test_size,
        "training_samples": len(data_frame),
        "routing": _metrics(route_y_test, routing_model.predict(route_x_test)),
        "sla": _metrics(sla_y_test, sla_model.predict(sla_x_test)),
    }
    return {"routing": routing_model, "sla": sla_model}, evaluation


class ModelService:
    """Load or train the AI triage models and serve predictions."""

    def __init__(
        self,
        model_path: Path | str = settings.model_path,
        data_path: Path | str = settings.data_path,
    ) -> None:
        self.model_path = Path(model_path)
        self.data_path = Path(data_path)
        self.routing_model: Pipeline | None = None
        self.sla_model: Pipeline | None = None
        self.evaluation: dict[str, Any] = {}
        self._lifecycle_lock = RLock()

    def _create_artifact(self, models: dict[str, Pipeline], data_frame: pd.DataFrame, evaluation: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_version": ARTIFACT_VERSION,
            "model_version": MODEL_VERSION,
            "feature_schema": list(FEATURE_COLUMNS),
            "routing_target": ROUTING_TARGET,
            "sla_target": f"{SLA_TARGET}: Yes=1, No=0",
            "training_samples": len(data_frame),
            "routing_classes": sorted(data_frame[ROUTING_TARGET].unique().tolist()),
            "evaluation": evaluation,
            "models": models,
        }

    def _load_artifact(self) -> dict[str, Any]:
        try:
            artifact = joblib.load(self.model_path)
        except Exception as error:
            raise ModelArtifactError("Unable to load model artifact.") from error
        if not isinstance(artifact, dict):
            raise ModelArtifactError("Model artifact is missing required metadata.")
        if artifact.get("artifact_version") != ARTIFACT_VERSION:
            raise ModelArtifactError("Model artifact version is unsupported.")
        if artifact.get("feature_schema") != list(FEATURE_COLUMNS):
            raise ModelArtifactError("Model artifact feature schema does not match the service.")
        models = artifact.get("models")
        if not isinstance(models, dict) or not isinstance(models.get("routing"), Pipeline) or not isinstance(models.get("sla"), Pipeline):
            raise ModelArtifactError("Model artifact must contain routing and SLA prediction pipelines.")
        return artifact

    def ensure_model(self) -> None:
        with self._lifecycle_lock:
            self._ensure_model()

    def _ensure_model(self) -> None:
        if self.model_path.exists():
            try:
                artifact = self._load_artifact()
                self.routing_model = artifact["models"]["routing"]
                self.sla_model = artifact["models"]["sla"]
                self.evaluation = artifact.get("evaluation", {})
                logger.info("model_loaded version=%s", artifact.get("model_version"))
                return
            except ModelArtifactError:
                logger.warning("Replacing an invalid or legacy model artifact at %s.", self.model_path)
                self.routing_model = self.sla_model = None

        if not settings.allow_model_training:
            raise ModelArtifactError(
                "Model artifact is unavailable and model training is disabled in this environment."
            )

        logger.info("model_training_started")
        raw_data = load_ticket_data(self.data_path)
        clean_data = validate_ticket_data(raw_data)
        models, evaluation = train_models(clean_data)
        artifact = self._create_artifact(models, clean_data, evaluation)

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.model_path.with_suffix(f"{self.model_path.suffix}.tmp")
        try:
            joblib.dump(artifact, temporary_path)
            temporary_path.replace(self.model_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        self.routing_model = models["routing"]
        self.sla_model = models["sla"]
        self.evaluation = evaluation
        logger.info("model_training_succeeded samples=%d", len(clean_data))

    def readiness(self) -> tuple[bool, str]:
        if self.routing_model is not None and self.sla_model is not None:
            return True, "loaded"
        if not self.model_path.exists():
            return False, "missing"
        try:
            artifact = self._load_artifact()
            self.routing_model = artifact["models"]["routing"]
            self.sla_model = artifact["models"]["sla"]
            self.evaluation = artifact.get("evaluation", {})
        except ModelArtifactError:
            return False, "invalid"
        return True, "loaded"

    def model_metadata(self) -> dict[str, Any]:
        return {
            "model_version": MODEL_VERSION,
            "artifact_version": ARTIFACT_VERSION,
            "feature_schema": list(FEATURE_COLUMNS),
            "training_samples": self.evaluation.get("training_samples"),
            "evaluation": self.evaluation,
        }

    def load_models(self) -> tuple[Pipeline, Pipeline]:
        if self.routing_model is None or self.sla_model is None:
            self.ensure_model()
        if self.routing_model is None or self.sla_model is None:
            raise ModelArtifactError("Models were not available after training.")
        return self.routing_model, self.sla_model

    def predict(
        self,
        *,
        summary: str,
        description: str | None,
        priority: str,
        created_hours: float,
        issue_type: str = "General",
        project: str = "General",
        component: str = "General",
        customer_tier: str = "Standard",
        channel: str = "Portal",
    ) -> dict[str, Any]:
        if priority not in settings.priority_map:
            raise ValueError(f"Unsupported priority: {priority!r}.")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("summary must be a non-empty string.")
        if not math.isfinite(created_hours) or created_hours < 0:
            raise ValueError("created_hours must be a finite, non-negative number.")

        routing_model, sla_model = self.load_models()
        features = pd.DataFrame([
            {
                "summary": summary.strip(),
                "description": (description or "").strip(),
                "priority": priority,
                "issue_type": issue_type or "General",
                "project": project or "General",
                "component": component or "General",
                "customer_tier": customer_tier or "Standard",
                "channel": channel or "Portal",
                "created_hours": created_hours,
            }
        ], columns=FEATURE_COLUMNS)

        route_proba = routing_model.predict_proba(features)[0]
        route_classes = routing_model.named_steps["classifier"].classes_
        route_index = int(route_proba.argmax())
        recommended_team = str(route_classes[route_index])
        route_confidence = float(route_proba[route_index])

        sla_proba = sla_model.predict_proba(features)[0]
        sla_high_probability = float(sla_proba[1])
        sla_risk = "High" if sla_high_probability >= 0.5 else "Low"

        reasons: list[str] = []
        if priority == "High":
            reasons.append("High priority increases urgency.")
        if created_hours >= 8:
            reasons.append("Ticket age is already above 8 hours.")
        if issue_type and issue_type != "General":
            reasons.append(f"Issue type is {issue_type}.")
        if not reasons:
            reasons.append("Recommendation is primarily driven by ticket text and metadata.")

        return {
            "assigned_team": recommended_team,
            "recommended_team": recommended_team,
            "routing_confidence": round(route_confidence, 4),
            "sla_breach_risk": sla_risk,
            "sla_probability": round(sla_high_probability, 4),
            "explanation": reasons,
            "model_version": MODEL_VERSION,
            "feature_schema": list(FEATURE_COLUMNS),
        }
