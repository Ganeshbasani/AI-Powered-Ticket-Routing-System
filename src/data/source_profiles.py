"""Explicit source mappings that refuse to infer unresolved JIRA semantics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.data.provenance import FieldProvenance, RecordOrigin


class SourceProfileError(ValueError):
    """Raised when a source profile cannot prove an authoritative mapping."""


@dataclass(frozen=True)
class SourceFieldMapping:
    canonical_field: str
    source_field_id: str
    source_event_id_field: str | None = None
    source_timestamp_field: str | None = None
    extraction_timestamp_field: str | None = None
    source_actor_field: str | None = None
    decision_source: str | None = None


@dataclass(frozen=True)
class TimestampSemantic:
    """Documents a source timestamp's intended canonical meaning without inventing policy."""

    canonical_field: str
    source_field_id: str
    required_at_prediction_time: bool


@dataclass(frozen=True)
class ResolvedSourceValue:
    value: str
    provenance: FieldProvenance


@dataclass(frozen=True)
class SourceProfile:
    """A configured profile is required before a source can create targets."""

    name: str
    source_system: str
    mappings: tuple[SourceFieldMapping, ...] = ()
    timestamp_semantics: tuple[TimestampSemantic, ...] = ()
    routing_vocabulary: frozenset[str] | None = None
    source_ticket_version_field: str | None = None
    configured: bool = False

    def mapping_for(self, canonical_field: str) -> SourceFieldMapping:
        if not self.configured:
            raise SourceProfileError(f"Source profile '{self.name}' is unconfigured; {canonical_field} cannot be inferred.")
        for mapping in self.mappings:
            if mapping.canonical_field == canonical_field:
                return mapping
        raise SourceProfileError(f"Source profile '{self.name}' has no mapping for {canonical_field}.")

    def resolve_initial_triage_team(self, record: Mapping[str, object]) -> ResolvedSourceValue:
        mapping = self.mapping_for("initial_triage_team")
        if not self.routing_vocabulary:
            raise SourceProfileError(f"Source profile '{self.name}' has no approved routing vocabulary.")
        value = record.get(mapping.source_field_id)
        event_id = record.get(mapping.source_event_id_field) if mapping.source_event_id_field else None
        decided_at = record.get(mapping.source_timestamp_field) if mapping.source_timestamp_field else None
        extracted_at = record.get(mapping.extraction_timestamp_field) if mapping.extraction_timestamp_field else None
        if not isinstance(value, str) or not value.strip():
            raise SourceProfileError("Initial triage team is missing from the configured source field.")
        if value not in self.routing_vocabulary:
            raise SourceProfileError(f"Unsupported routing team from source profile: {value!r}.")
        if not isinstance(event_id, str) or not event_id.strip() or not isinstance(decided_at, str) or not decided_at.strip() or not isinstance(extracted_at, str) or not extracted_at.strip():
            raise SourceProfileError("Authoritative initial routing requires source event, event timestamp, and extraction timestamp evidence.")
        actor = record.get(mapping.source_actor_field) if mapping.source_actor_field else None
        provenance = FieldProvenance(
            source_system=self.source_system,
            source_event_id=event_id,
            source_field_id=mapping.source_field_id,
            event_timestamp=decided_at,
            extraction_timestamp=extracted_at,
            source_ticket_version=(
                record.get(self.source_ticket_version_field)
                if self.source_ticket_version_field and isinstance(record.get(self.source_ticket_version_field), str)
                else None
            ),
            actor_identity=actor if isinstance(actor, str) else None,
            decision_source=mapping.decision_source,
            record_origin=RecordOrigin.OBSERVED,
        )
        return ResolvedSourceValue(value=value, provenance=provenance)

    def mapping_for_sla_field(self, canonical_field: str) -> SourceFieldMapping:
        """Resolve only explicitly configured SLA mappings; policy semantics stay external."""
        return self.mapping_for(canonical_field)

    def mapping_for_text_field(self, canonical_field: str) -> SourceFieldMapping:
        """Resolve only explicitly configured pre-ticket text mappings."""
        if canonical_field not in {"summary", "description"}:
            raise SourceProfileError(f"{canonical_field} is not a canonical text field.")
        return self.mapping_for(canonical_field)

    def timestamp_semantic_for(self, canonical_field: str) -> TimestampSemantic:
        """Require a source profile to declare timestamp meaning before historical use."""
        if not self.configured:
            raise SourceProfileError(f"Source profile '{self.name}' is unconfigured; timestamp semantics are unavailable.")
        for semantic in self.timestamp_semantics:
            if semantic.canonical_field == canonical_field:
                return semantic
        raise SourceProfileError(f"Source profile '{self.name}' has no timestamp semantics for {canonical_field}.")


UNCONFIGURED_SOURCE_PROFILE = SourceProfile(name="unconfigured", source_system="unconfigured")

# This describes the integration shape only. It deliberately contains no JIRA
# field IDs, vocabulary, SLA policy, or privacy settings until an owner configures them.
JIRA_SERVICE_MANAGEMENT_CLOUD_REFERENCE = SourceProfile(
    name="jira_service_management_cloud_reference",
    source_system="jira_service_management_cloud",
    configured=False,
)
