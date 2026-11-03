"""Reusable, source-neutral provenance records for future data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ProvenanceError(ValueError):
    """Raised when a record lacks the evidence required for historical use."""


class RecordOrigin(str, Enum):
    OBSERVED = "observed"
    SYNTHETIC = "synthetic"


DECISION_SOURCES = frozenset({"human", "automation", "hybrid", "unknown"})


def _parse_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ProvenanceError("Timestamp must be ISO-8601.") from error
    if parsed.tzinfo is None:
        raise ProvenanceError("Timestamp must include a timezone.")


@dataclass(frozen=True)
class FieldProvenance:
    source_system: str
    source_event_id: str
    source_field_id: str
    event_timestamp: str
    extraction_timestamp: str
    source_ticket_version: str | None = None
    actor_identity: str | None = None
    decision_source: str | None = None
    record_origin: RecordOrigin = RecordOrigin.OBSERVED

    def __post_init__(self) -> None:
        for name in ("source_system", "source_event_id", "source_field_id"):
            if not getattr(self, name).strip():
                raise ProvenanceError(f"{name} is required.")
        _parse_timestamp(self.event_timestamp)
        _parse_timestamp(self.extraction_timestamp)
        if self.decision_source is not None and self.decision_source not in DECISION_SOURCES:
            raise ProvenanceError(f"decision_source must be one of {sorted(DECISION_SOURCES)}.")


def validate_provenance_complete(provenance: FieldProvenance, *, require_ticket_version: bool = False) -> None:
    """Require source version evidence where a historical reconstruction needs it."""
    if require_ticket_version and not provenance.source_ticket_version:
        raise ProvenanceError("source_ticket_version is required for historical reconstruction.")
