"""Focused regression tests for Phase 8C architecture-only contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from src.config.settings import settings
from src.data.contract import (
    CANONICAL_COLUMNS,
    FeatureContractError,
    PREDICTION_SNAPSHOT_FIELDS,
    validate_prediction_feature_fields,
)
from src.data.pipeline import ingest
from src.data.provenance import FieldProvenance, RecordOrigin
from src.data.snapshots import PredictionSnapshot, SnapshotContractError
from src.data.source_profiles import (
    UNCONFIGURED_SOURCE_PROFILE,
    SourceFieldMapping,
    SourceProfile,
    SourceProfileError,
    TimestampSemantic,
)


def test_unconfigured_profile_cannot_create_authoritative_routing_target():
    with pytest.raises(SourceProfileError, match="unconfigured"):
        UNCONFIGURED_SOURCE_PROFILE.resolve_initial_triage_team({"assigned_team": "L1"})


def test_configured_profile_requires_event_evidence_and_approved_team():
    profile = SourceProfile(
        name="approved-test-source",
        source_system="test",
        configured=True,
        routing_vocabulary=frozenset({"Team-A"}),
        mappings=(
            SourceFieldMapping(
                canonical_field="initial_triage_team",
                source_field_id="routing_team",
                source_event_id_field="routing_event_id",
                source_timestamp_field="routing_decided_at",
                extraction_timestamp_field="extracted_at",
                decision_source="automation",
            ),
        ),
        timestamp_semantics=(TimestampSemantic("created_timestamp", "created", True),),
    )
    resolved = profile.resolve_initial_triage_team(
        {
            "routing_team": "Team-A",
            "routing_event_id": "event-1",
            "routing_decided_at": "2026-01-01T00:00:00+00:00",
            "extracted_at": "2026-01-02T00:00:00+00:00",
        }
    )
    assert resolved.value == "Team-A"
    assert resolved.provenance.decision_source == "automation"
    with pytest.raises(SourceProfileError, match="event"):
        profile.resolve_initial_triage_team({"routing_team": "Team-A"})
    assert profile.timestamp_semantic_for("created_timestamp").required_at_prediction_time is True
    with pytest.raises(SourceProfileError, match="no mapping"):
        profile.mapping_for_sla_field("actual_sla_breach")
    with pytest.raises(SourceProfileError, match="not a canonical text"):
        profile.mapping_for_text_field("final_status")


def test_legacy_csv_is_readable_without_creating_authoritative_routing_target():
    legacy = pd.read_csv(settings.data_path)
    frame = ingest(settings.data_path)
    assert list(legacy.columns) == ["ticket_id", "priority", "issue_type", "created_hours", "assigned_team", "sla_breach"]
    assert tuple(frame.columns) == CANONICAL_COLUMNS
    assert frame["assigned_team"].tolist() == ["L2", "L1", "L3"]
    assert frame["initial_triage_team"].isna().all()
    assert frame["final_team"].isna().all()


@pytest.mark.parametrize("field", ["final_team", "actual_sla_breach", "sla_breach", "ticket_id"])
def test_targets_outcomes_and_identifiers_cannot_be_prediction_features(field):
    with pytest.raises(FeatureContractError, match="cannot be prediction features"):
        validate_prediction_feature_fields(["priority", field])


def test_mutable_state_requires_historical_provenance():
    with pytest.raises(FeatureContractError, match="require historical source provenance"):
        validate_prediction_feature_fields(["assigned_team"])
    validate_prediction_feature_fields(["assigned_team"], historical_provenance={"assigned_team": object()})


def test_snapshot_contract_is_immutable_and_contains_required_fields():
    snapshot = PredictionSnapshot.create(
        prediction_snapshot_id="snapshot-1",
        ticket_id="1",
        source_ticket_key="TEST-1",
        source_ticket_version="version-1",
        scored_at="2026-01-01T01:00:00+00:00",
        feature_values={"priority": "High", "created_hours": 1.0},
        feature_schema_version="phase8c-1",
        model_version="phase3-1",
        model_artifact_sha256="a" * 64,
        text_normalization_version=None,
        source_event_ids={"priority": "event-1", "created_hours": "event-2"},
        source_system="test",
        record_origin=RecordOrigin.OBSERVED,
        synthetic=False,
    )
    assert set(PREDICTION_SNAPSHOT_FIELDS) == set(snapshot.__dataclass_fields__)
    assert snapshot.feature_values == {"created_hours": 1.0, "priority": "High"}
    with pytest.raises(FrozenInstanceError):
        snapshot.model_version = "changed"  # type: ignore[misc]
    with pytest.raises(SnapshotContractError, match="cannot be prediction features"):
        PredictionSnapshot.create(
            prediction_snapshot_id="snapshot-2", ticket_id="1", source_ticket_key="TEST-1",
            source_ticket_version="version-1", scored_at="2026-01-01T01:00:00+00:00",
            feature_values={"actual_sla_breach": "Yes"}, feature_schema_version="phase8c-1",
            model_version="phase3-1", model_artifact_sha256="a" * 64, text_normalization_version=None,
            source_event_ids={}, source_system="test", record_origin=RecordOrigin.OBSERVED, synthetic=False,
        )


def test_provenance_requires_event_and_extraction_timestamps():
    with pytest.raises(ValueError, match="timezone"):
        FieldProvenance(
            source_system="test", source_event_id="event-1", source_field_id="priority",
            event_timestamp="2026-01-01T00:00:00", extraction_timestamp="2026-01-01T01:00:00+00:00",
        )
