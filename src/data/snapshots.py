"""Immutable prediction-time snapshot contract; persistence is intentionally deferred."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.data.contract import PREDICTION_SNAPSHOT_FIELDS, validate_prediction_feature_fields
from src.data.provenance import RecordOrigin


class SnapshotContractError(ValueError):
    """Raised when a snapshot cannot prove its immutable scoring context."""


def _parse_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise SnapshotContractError("scored_at must be ISO-8601.") from error
    if parsed.tzinfo is None:
        raise SnapshotContractError("scored_at must include a timezone.")


def _json_object(value: str, name: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise SnapshotContractError(f"{name} must contain a JSON object.") from error
    if not isinstance(decoded, dict):
        raise SnapshotContractError(f"{name} must contain a JSON object.")
    return decoded


@dataclass(frozen=True)
class PredictionSnapshot:
    """Serialized JSON payloads prevent mutation after a scoring event is captured."""

    prediction_snapshot_id: str
    ticket_id: str
    source_ticket_key: str
    source_ticket_version: str
    scored_at: str
    feature_snapshot_json: str
    feature_schema_version: str
    model_version: str
    model_artifact_sha256: str
    text_normalization_version: str | None
    source_event_ids: str
    source_system: str
    record_origin: RecordOrigin
    synthetic: bool
    generator_version: str | None = None
    rule_set_version: str | None = None
    seed: int | None = None

    def __post_init__(self) -> None:
        for field in ("prediction_snapshot_id", "ticket_id", "source_ticket_key", "source_ticket_version", "feature_schema_version", "model_version", "model_artifact_sha256", "source_system"):
            if not getattr(self, field).strip():
                raise SnapshotContractError(f"{field} is required.")
        _parse_timestamp(self.scored_at)
        features = _json_object(self.feature_snapshot_json, "feature_snapshot_json")
        _json_object(self.source_event_ids, "source_event_ids")
        try:
            validate_prediction_feature_fields(features.keys())
        except ValueError as error:
            raise SnapshotContractError(str(error)) from error
        if self.synthetic != (self.record_origin is RecordOrigin.SYNTHETIC):
            raise SnapshotContractError("synthetic must match record_origin.")
        if self.synthetic and (not self.generator_version or not self.rule_set_version or self.seed is None):
            raise SnapshotContractError("Synthetic snapshots require generator_version, rule_set_version, and seed.")

    @property
    def feature_values(self) -> dict[str, Any]:
        return _json_object(self.feature_snapshot_json, "feature_snapshot_json")

    @property
    def source_events(self) -> dict[str, Any]:
        return _json_object(self.source_event_ids, "source_event_ids")

    @classmethod
    def create(cls, *, feature_values: dict[str, Any], source_event_ids: dict[str, Any], **values: Any) -> "PredictionSnapshot":
        """Build a snapshot with canonical JSON ordering for stable integrity checks."""
        return cls(
            feature_snapshot_json=json.dumps(feature_values, sort_keys=True, separators=(",", ":")),
            source_event_ids=json.dumps(source_event_ids, sort_keys=True, separators=(",", ":")),
            **values,
        )


assert set(PREDICTION_SNAPSHOT_FIELDS) == set(PredictionSnapshot.__dataclass_fields__)
