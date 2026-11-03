"""Versioned canonical dataset contract and feature registry."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum

LEGACY_SCHEMA_VERSION = "1.0"
SCHEMA_VERSION = "1.1"
PREDICTION_FIELDS = ("priority", "created_hours", "issue_type", "project", "component", "summary", "description", "created_timestamp")
ROUTING_TARGET_FIELDS = (
    "initial_triage_team", "initial_triage_decided_at", "initial_triage_event_id",
    "initial_triage_decision_source", "initial_triage_source_system", "initial_triage_is_automated",
)
PREDICTION_TARGET_FIELDS = ("initial_triage_team", "actual_sla_breach")
SLA_OUTCOME_FIELDS = (
    "actual_sla_breach", "sla_outcome_state", "sla_clock_started_at", "sla_deadline_at",
    "sla_breach_observed_at", "sla_outcome_observed_at", "sla_policy_id", "sla_policy_version",
    "sla_pause_seconds", "sla_extension_seconds", "sla_source_event_id",
)
OUTCOME_FIELDS = (*SLA_OUTCOME_FIELDS, "resolution_timestamp", "resolution_time", "final_status", "final_team")
MUTABLE_PLATFORM_FIELDS = ("assigned_team", "status", "updated_at")
METADATA_FIELDS = ("dataset_version", "ingestion_source", "imported_at")
IDENTIFIER_FIELDS = ("ticket_id", "jira_issue_key")
CANONICAL_COLUMNS = (
    *IDENTIFIER_FIELDS, *PREDICTION_FIELDS, *ROUTING_TARGET_FIELDS,
    *MUTABLE_PLATFORM_FIELDS, *OUTCOME_FIELDS, *METADATA_FIELDS,
)
PREDICTION_SNAPSHOT_FIELDS = (
    "prediction_snapshot_id", "ticket_id", "source_ticket_key", "source_ticket_version", "scored_at",
    "feature_snapshot_json", "feature_schema_version", "model_version", "model_artifact_sha256",
    "text_normalization_version", "source_event_ids", "source_system", "record_origin", "synthetic",
    "generator_version", "rule_set_version", "seed",
)


class FieldClassification(str, Enum):
    PREDICTION_FEATURE = "prediction_feature"
    PREDICTION_TARGET = "prediction_target"
    POST_RESOLUTION_OUTCOME = "post_resolution_outcome"
    MUTABLE_PLATFORM_STATE = "mutable_platform_state"
    METADATA_PROVENANCE = "metadata/provenance"
    DERIVED_FEATURE = "derived_feature"
    FORBIDDEN_LEAKAGE = "forbidden_leakage"
    IDENTIFIER = "identifier"


class FeatureContractError(ValueError):
    """Raised when a proposed feature violates the canonical contract."""


FIELD_CLASSIFICATIONS = {
    **{field: FieldClassification.PREDICTION_FEATURE for field in PREDICTION_FIELDS},
    **{field: FieldClassification.PREDICTION_TARGET for field in PREDICTION_TARGET_FIELDS},
    **{field: FieldClassification.METADATA_PROVENANCE for field in ROUTING_TARGET_FIELDS if field != "initial_triage_team"},
    "actual_sla_breach": FieldClassification.PREDICTION_TARGET,
    "sla_breach": FieldClassification.PREDICTION_TARGET,
    **{field: FieldClassification.POST_RESOLUTION_OUTCOME for field in OUTCOME_FIELDS if field != "actual_sla_breach"},
    **{field: FieldClassification.MUTABLE_PLATFORM_STATE for field in MUTABLE_PLATFORM_FIELDS},
    **{field: FieldClassification.METADATA_PROVENANCE for field in METADATA_FIELDS},
    "predicted_at": FieldClassification.METADATA_PROVENANCE,
    "scored_at": FieldClassification.METADATA_PROVENANCE,
    "normalized_text": FieldClassification.DERIVED_FEATURE,
    "combined_text": FieldClassification.DERIVED_FEATURE,
    "outcome_text": FieldClassification.FORBIDDEN_LEAKAGE,
    **{field: FieldClassification.IDENTIFIER for field in IDENTIFIER_FIELDS},
}


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    feature_type: str
    prediction_time: bool
    description: str
    preprocessing: str
    leakage_risk: str


FEATURE_REGISTRY = {
    "priority": FeatureDefinition("priority", "categorical", True, "Ticket priority at prediction time", "ordinal encode", "low"),
    "created_hours": FeatureDefinition("created_hours", "numeric", True, "Elapsed ticket age at prediction time", "finite non-negative float", "medium"),
    "issue_type": FeatureDefinition("issue_type", "categorical", True, "Ticket issue type", "categorical encode when introduced", "low"),
    "summary": FeatureDefinition("summary", "text", True, "Ticket summary", "deterministic normalization; combine with description for TF-IDF", "medium"),
    "description": FeatureDefinition("description", "text", True, "Ticket description", "deterministic normalization; combine with summary for TF-IDF", "medium"),
    "created_timestamp": FeatureDefinition("created_timestamp", "timestamp", True, "Ticket creation timestamp", "chronological split anchor", "low"),
    "initial_triage_team": FeatureDefinition("initial_triage_team", "label", False, "First authoritative team-routing decision", "target only; requires source profile", "critical"),
    "assigned_team": FeatureDefinition("assigned_team", "categorical", False, "Mutable platform assignment", "exclude without historical provenance", "critical"),
    "actual_sla_breach": FeatureDefinition("actual_sla_breach", "label", False, "Observed SLA outcome", "target only", "critical"),
    "final_status": FeatureDefinition("final_status", "categorical", False, "Status after ticket completion", "exclude", "critical"),
    "final_team": FeatureDefinition("final_team", "categorical", False, "Final resolving team", "exclude", "critical"),
}


def prediction_time_columns() -> tuple[str, ...]:
    """Return canonical columns that are permitted as model inputs."""
    return tuple(definition.name for definition in FEATURE_REGISTRY.values() if definition.prediction_time)


def classify_field(field: str) -> FieldClassification:
    """Return the explicit safety classification for a known canonical field."""
    try:
        return FIELD_CLASSIFICATIONS[field]
    except KeyError as error:
        raise FeatureContractError(f"Unknown canonical field: {field}.") from error


def validate_prediction_feature_fields(
    fields: Collection[str], *, historical_provenance: Mapping[str, object] | None = None
) -> None:
    """Reject targets, outcomes, identifiers, and unproven mutable state as features."""
    historical_provenance = historical_provenance or {}
    disallowed: list[str] = []
    unproven_mutable: list[str] = []
    for field in fields:
        classification = classify_field(field)
        if classification in {
            FieldClassification.PREDICTION_TARGET,
            FieldClassification.POST_RESOLUTION_OUTCOME,
            FieldClassification.IDENTIFIER,
            FieldClassification.FORBIDDEN_LEAKAGE,
        }:
            disallowed.append(field)
        elif classification is FieldClassification.MUTABLE_PLATFORM_STATE and field not in historical_provenance:
            unproven_mutable.append(field)
    if disallowed:
        raise FeatureContractError(f"Fields cannot be prediction features: {', '.join(sorted(disallowed))}.")
    if unproven_mutable:
        raise FeatureContractError(
            "Mutable fields require historical source provenance: " + ", ".join(sorted(unproven_mutable)) + "."
        )
