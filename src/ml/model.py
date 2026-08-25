"""Model training and prediction utilities."""

from __future__ import annotations

import math
import logging
from pathlib import Path
from threading import RLock

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from src.config.settings import settings
from src.ml.data_processing import (
    FEATURE_COLUMNS,
    load_ticket_data,
    prepare_features,
    prepare_labels,
    validate_ticket_data,
)

ARTIFACT_VERSION = 1
MODEL_VERSION = "phase3-1"
logger = logging.getLogger("sla_prediction.model")


class ModelArtifactError(ValueError):
    """Raised when a saved model artifact cannot be safely used."""


def build_pipeline() -> Pipeline:
    """Build the shared preprocessing and classification pipeline."""
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "priority",
                OrdinalEncoder(categories=[list(settings.priority_map)], handle_unknown="error"),
                ["priority"],
            ),
            ("created_hours", "passthrough", ["created_hours"]),
        ],
        verbose_feature_names_out=False,
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocessor),
            ("classifier", RandomForestClassifier(random_state=42)),
        ]
    )


def train_model(data_frame: pd.DataFrame) -> Pipeline:
    features = prepare_features(data_frame)
    target = prepare_labels(data_frame)

    pipeline = build_pipeline()
    pipeline.fit(features, target)
    return pipeline


class ModelService:
    """Train and load the SLA breach model."""

    def __init__(
        self,
        model_path: Path | str = settings.model_path,
        data_path: Path | str = settings.data_path,
    ) -> None:
        self.model_path = Path(model_path)
        self.data_path = Path(data_path)
        self.model: Pipeline | None = None
        self._lifecycle_lock = RLock()

    def _create_artifact(self, model: Pipeline, data_frame: pd.DataFrame) -> dict:
        class_distribution = data_frame["sla_breach"].value_counts().sort_index().to_dict()
        return {
            "artifact_version": ARTIFACT_VERSION,
            "model_version": MODEL_VERSION,
            "feature_schema": list(FEATURE_COLUMNS),
            "target_definition": "sla_breach: Yes=1, No=0",
            "training_samples": len(data_frame),
            "class_distribution": class_distribution,
            "evaluation": {
                "status": "not_available",
                "reason": "The dataset is too small for a valid held-out evaluation.",
            },
            "pipeline": model,
        }

    def _load_artifact(self) -> Pipeline:
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

        pipeline = artifact.get("pipeline")
        if not isinstance(pipeline, Pipeline):
            raise ModelArtifactError("Model artifact does not contain a prediction pipeline.")
        return pipeline

    def ensure_model(self) -> None:
        """Load or build an artifact without concurrent in-process replacement."""
        with self._lifecycle_lock:
            self._ensure_model()

    def _ensure_model(self) -> None:
        if self.model_path.exists():
            try:
                self.model = self._load_artifact()
                logger.info("model_loaded")
                return
            except ModelArtifactError:
                logger.warning("Replacing an invalid or legacy model artifact at %s.", self.model_path)
                self.model = None

        logger.info("model_training_started")
        raw_data = load_ticket_data(self.data_path)
        clean_data = validate_ticket_data(raw_data)
        model = train_model(clean_data)
        artifact = self._create_artifact(model, clean_data)

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.model_path.with_suffix(f"{self.model_path.suffix}.tmp")
        try:
            joblib.dump(artifact, temporary_path)
            temporary_path.replace(self.model_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        self.model = model
        logger.info("model_training_succeeded")

    def load_model(self) -> Pipeline:
        if self.model is not None:
            return self.model

        self.ensure_model()
        if self.model is None:
            raise ModelArtifactError("Model was not available after training.")
        return self.model

    def readiness(self) -> tuple[bool, str]:
        """Check whether a valid artifact is immediately available without training."""
        if self.model is not None:
            return True, "loaded"
        if not self.model_path.exists():
            return False, "missing"
        try:
            self.model = self._load_artifact()
        except ModelArtifactError:
            return False, "invalid"
        return True, "loaded"

    def predict(self, priority: str, created_hours: float) -> dict[str, str]:
        if priority not in settings.priority_map:
            raise ValueError(f"Unsupported priority: {priority!r}.")
        if not math.isfinite(created_hours) or created_hours < 0:
            raise ValueError("created_hours must be a finite, non-negative number.")

        model = self.load_model()
        features = pd.DataFrame([[priority, created_hours]], columns=FEATURE_COLUMNS)
        prediction = model.predict(features)[0]

        return {
            "assigned_team": "L2" if priority == "High" else "L1",
            "sla_breach_risk": "High" if prediction else "Low",
            "model_version": MODEL_VERSION,
        }
