"""Isolated synthetic-development candidate inference for recruiter demos."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from threading import RLock
from typing import Any

import joblib
import pandas as pd
from sklearn.pipeline import Pipeline

from src.config.settings import settings
from src.data.contract import validate_prediction_feature_fields
from src.data.nlp import combine_ticket_text
from src.ml.candidates import (
    CANDIDATE_FEATURE_SCHEMA_VERSION,
    CANDIDATE_MODEL_VERSION,
    STRUCTURED_FEATURES,
)

OBSERVED_MODEL_VERSION = "observed-v1"


class CandidateArtifactError(ValueError):
    """Raised when an isolated candidate artifact is missing or invalid."""


class CandidateModelService:
    """Load checksum-verified candidates without replacing the live baseline."""

    def __init__(self, artifact_directory: Path | str | None = None) -> None:
        self.artifact_directory = Path(artifact_directory or settings.model_path.parent / "candidates")
        self._artifacts: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def _paths(self, kind: str) -> list[tuple[Path, Path]]:
        if kind not in {"routing", "sla"}:
            raise ValueError("Candidate kind must be routing or sla.")
        observed = self.artifact_directory.parent / "verified" / f"{kind}-{OBSERVED_MODEL_VERSION}.joblib"
        synthetic = self.artifact_directory / f"{kind}-{CANDIDATE_MODEL_VERSION}.joblib"
        return [(observed, observed.with_suffix(observed.suffix + ".manifest.json")),
                (synthetic, synthetic.with_suffix(synthetic.suffix + ".manifest.json"))]

    def _load(self, kind: str) -> dict[str, Any]:
        with self._lock:
            if kind in self._artifacts:
                return self._artifacts[kind]
            paths = self._paths(kind)
            selected = next(((artifact, manifest) for artifact, manifest in paths if artifact.exists() or manifest.exists()), None)
            if selected is None:
                raise CandidateArtifactError(f"The {kind} candidate has not been trained.")
            artifact_path, manifest_path = selected
            if not artifact_path.is_file() or not manifest_path.is_file():
                raise CandidateArtifactError(f"The {kind} candidate artifact or manifest is missing.")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                if manifest.get("artifact_sha256") != digest:
                    raise CandidateArtifactError(f"The {kind} candidate checksum does not match its manifest.")
                artifact = joblib.load(artifact_path)
            except CandidateArtifactError:
                raise
            except Exception as error:
                raise CandidateArtifactError(f"Unable to load the {kind} candidate artifact.") from error

            expected_target = "initial_triage_team" if kind == "routing" else "actual_sla_breach"
            expected_schema = [*STRUCTURED_FEATURES, "combined_text"]
            if not isinstance(artifact, dict):
                raise CandidateArtifactError("Candidate artifact metadata is missing.")
            if artifact.get("kind") != kind or artifact.get("target") != expected_target:
                raise CandidateArtifactError("Candidate kind or target does not match the requested model.")
            if artifact.get("model_version") not in {CANDIDATE_MODEL_VERSION, OBSERVED_MODEL_VERSION}:
                raise CandidateArtifactError("Candidate model version is unsupported.")
            if artifact.get("feature_schema_version") != CANDIDATE_FEATURE_SCHEMA_VERSION or artifact.get("feature_schema") != expected_schema:
                raise CandidateArtifactError("Candidate feature schema is unsupported.")
            expected_origin = "observed" if artifact.get("model_version") == OBSERVED_MODEL_VERSION else "synthetic"
            artifact_origin = artifact.get("data_origin") or artifact.get("evaluation", {}).get("data_origin")
            if artifact_origin != expected_origin or artifact.get("evaluation", {}).get("data_origin") != expected_origin:
                raise CandidateArtifactError("Candidate evaluation provenance does not match its model version.")
            pipeline = artifact.get("pipeline")
            if not isinstance(pipeline, Pipeline):
                raise CandidateArtifactError("Candidate artifact does not contain a prediction pipeline.")
            if manifest.get("model_version") != artifact.get("model_version") or manifest.get("kind") != kind:
                raise CandidateArtifactError("Candidate manifest metadata does not match the artifact.")
            artifact["artifact_sha256"] = digest
            self._artifacts[kind] = artifact
            return artifact

    def status(self) -> dict[str, Any]:
        result = {}
        for kind in ("routing", "sla"):
            try:
                artifact = self._load(kind)
                result[kind] = {
                    "available": True,
                    "model_version": artifact["model_version"],
                    "training_samples": artifact["training_samples"],
                    "training_manifest_checksum": artifact.get("training_manifest_checksum") or artifact.get("manifest_sha256"),
                    "artifact_sha256": artifact["artifact_sha256"],
                    "evaluation": artifact["evaluation"],
                    "data_origin": artifact.get("data_origin") or artifact["evaluation"].get("data_origin"),
                }
            except CandidateArtifactError as error:
                result[kind] = {"available": False, "reason": str(error)}
        return result

    def predict(self, ticket: dict[str, Any]) -> dict[str, Any]:
        validate_prediction_feature_fields(STRUCTURED_FEATURES)
        priority = ticket.get("priority")
        try:
            created_hours = float(ticket.get("created_hours"))
        except (TypeError, ValueError) as error:
            raise ValueError("Ticket age must be numeric for candidate prediction.") from error
        if priority not in settings.priority_map or not math.isfinite(created_hours) or created_hours < 0:
            raise ValueError("Ticket priority or age is invalid for candidate prediction.")

        features = pd.DataFrame([{
            "priority": priority,
            # These fields are not currently stored by the ticket platform.
            # Unknown is an explicit, ignored category in the one-hot encoder.
            "issue_type": "Unknown",
            "project": "Unknown",
            "component": "Unknown",
            "created_hours": created_hours,
            "combined_text": combine_ticket_text(ticket),
        }], columns=[*STRUCTURED_FEATURES, "combined_text"])

        predictions: dict[str, Any] = {}
        for kind in ("routing", "sla"):
            artifact = self._load(kind)
            pipeline = artifact["pipeline"]
            probabilities = pipeline.predict_proba(features)[0]
            classes = list(pipeline.classes_)
            best_index = int(probabilities.argmax())
            scores = [
                {"label": str(label), "score_percent": round(float(probability) * 100, 1)}
                for label, probability in zip(classes, probabilities)
            ]
            scores.sort(key=lambda item: item["score_percent"], reverse=True)
            confidence = scores[0]["score_percent"]
            margin = round(confidence - scores[1]["score_percent"], 1) if len(scores) > 1 else confidence
            try:
                minimum_confidence = float(os.environ.get("ML_MIN_CONFIDENCE_PERCENT", "55"))
                minimum_margin = float(os.environ.get("ML_MIN_MARGIN_PERCENT", "10"))
            except ValueError as error:
                raise ValueError("ML confidence thresholds must be numeric percentages.") from error
            if not 0 <= minimum_confidence <= 100 or not 0 <= minimum_margin <= 100:
                raise ValueError("ML confidence thresholds must be between 0 and 100.")
            origin = artifact.get("data_origin") or artifact["evaluation"].get("data_origin", "unknown")
            review_reasons: list[str] = []
            if confidence < minimum_confidence:
                review_reasons.append(
                    f"Top model score {confidence:.1f}% is below the {minimum_confidence:g}% review threshold."
                )
            if margin < minimum_margin:
                review_reasons.append(
                    f"The top two classes differ by only {margin:.1f} points; the routing decision is ambiguous."
                )
            if origin == "synthetic":
                review_reasons.append(
                    "This candidate was trained on synthetic data and has no validated real-world performance."
                )
            try:
                structured = pipeline.named_steps["preprocess"].named_transformers_["structured"]
                supported_priorities = {str(value) for value in structured.categories_[0]}
            except (AttributeError, KeyError, IndexError, TypeError):
                supported_priorities = set()
            if priority not in supported_priorities:
                review_reasons.append(
                    f"Priority {priority!r} was not represented in this model's training data."
                )
            payload = {
                "prediction": str(classes[best_index]),
                "score_percent": confidence,
                "margin_percent": margin,
                "review_required": bool(review_reasons),
                "review_reasons": review_reasons,
                "class_scores": scores,
                "training_samples": artifact["training_samples"],
                "artifact_sha256": artifact["artifact_sha256"],
                "model_version": artifact["model_version"],
                "data_origin": origin,
                "evaluation": artifact["evaluation"],
            }
            predictions[kind] = payload

        origins = {predictions[kind]["data_origin"] for kind in ("routing", "sla")}
        if len(origins) != 1:
            raise CandidateArtifactError("Routing and SLA artifacts have different data provenance; retrain or restore the model pair.")
        predictions["data_origin"] = next(iter(origins))
        predictions["model_version"] = predictions["routing"]["model_version"]
        predictions["warning"] = (
            "Observed-label models were evaluated on a chronological holdout; results are not a guarantee of future performance."
            if origins == {"observed"} else
            "Experimental candidates were trained and evaluated on synthetic data. Scores are uncalibrated and are not evidence of real-world performance."
        )
        predictions["missing_metadata"] = ["issue_type", "project", "component"]
        predictions["features"] = {
            "priority": priority,
            "created_hours": round(created_hours, 4),
            "text_fields": [field for field in ("summary", "description") if str(ticket.get(field) or "").strip()],
        }
        predictions["metadata"] = {
            "data_origin": predictions["data_origin"],
            "real_world_performance_claim": False,
            "warning": predictions["warning"],
            "missing_metadata": predictions["missing_metadata"],
            "models": {
                kind: {
                    "model_version": predictions[kind]["model_version"],
                    "training_samples": predictions[kind]["training_samples"],
                    "artifact_sha256": predictions[kind]["artifact_sha256"],
                    "evaluation": predictions[kind]["evaluation"],
                    "review_reasons": predictions[kind]["review_reasons"],
                }
                for kind in ("routing", "sla")
            },
        }
        return predictions
