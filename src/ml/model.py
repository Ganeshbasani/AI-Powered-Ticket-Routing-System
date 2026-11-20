"""Transparent policy assessment used as the live SLA fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config.settings import settings
from src.ml.sla_policy import SLA_POLICY_SHA256, SLA_POLICY_VERSION, assess_sla

MODEL_VERSION = SLA_POLICY_VERSION


class ModelArtifactError(ValueError):
    """Raised when callers try to use the retired three-row SLA classifier."""


def build_pipeline() -> Any:
    raise ModelArtifactError(
        "The legacy random-forest pipeline is retired; use the observed-data training workflow."
    )


def train_model(data_frame: Any) -> Any:
    raise ModelArtifactError(
        "The legacy random-forest trainer is retired; use `python -m src.cli train-observed` with provenance-attested history."
    )


class ModelService:
    """Expose the deterministic SLA policy; never load the retired model artifact."""

    def __init__(
        self,
        model_path: Path | str = settings.model_path,
        data_path: Path | str = settings.data_path,
    ) -> None:
        self.model_path = Path(model_path)
        self.data_path = Path(data_path)

    def ensure_model(self) -> None:
        raise ModelArtifactError(
            "The three-row SLA baseline is retired. Train an observed model with `python -m src.cli train-observed` after supplying validated historical data."
        )

    def load_model(self) -> Any:
        raise ModelArtifactError("The legacy random-forest baseline is not used by the live SLA policy.")

    def readiness(self) -> tuple[bool, str]:
        return False, "retired; live SLA assessment uses the explicit policy"

    def artifact_sha256(self) -> str:
        raise ModelArtifactError("The retired baseline artifact is not an active prediction model.")

    def predict(self, priority: str, created_hours: float) -> dict[str, Any]:
        assessment = assess_sla(priority, created_hours)
        return {
            **assessment,
            "assigned_team": "Unassigned",
            "model_version": SLA_POLICY_VERSION,
            "policy_sha256": SLA_POLICY_SHA256,
        }
