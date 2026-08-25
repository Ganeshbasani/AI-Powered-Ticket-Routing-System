"""Versioned canonical dataset contract and feature registry."""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "1.0"
PREDICTION_FIELDS = ("priority", "created_hours", "issue_type", "project", "component", "summary", "description", "created_timestamp")
OUTCOME_FIELDS = ("actual_sla_breach", "resolution_timestamp", "resolution_time", "final_status", "final_team")
METADATA_FIELDS = ("dataset_version", "ingestion_source", "imported_at")
IDENTIFIER_FIELDS = ("ticket_id", "jira_issue_key")
CANONICAL_COLUMNS = (*IDENTIFIER_FIELDS, *PREDICTION_FIELDS, *OUTCOME_FIELDS, *METADATA_FIELDS)


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
    "summary": FeatureDefinition("summary", "text", True, "Ticket summary", "future NLP pipeline", "low"),
    "description": FeatureDefinition("description", "text", True, "Ticket description", "future NLP pipeline", "low"),
    "created_timestamp": FeatureDefinition("created_timestamp", "timestamp", True, "Ticket creation timestamp", "chronological split anchor", "low"),
    "actual_sla_breach": FeatureDefinition("actual_sla_breach", "label", False, "Observed SLA outcome", "target only", "critical"),
    "final_status": FeatureDefinition("final_status", "categorical", False, "Status after ticket completion", "exclude", "critical"),
    "final_team": FeatureDefinition("final_team", "categorical", False, "Final resolving team", "exclude", "critical"),
}
