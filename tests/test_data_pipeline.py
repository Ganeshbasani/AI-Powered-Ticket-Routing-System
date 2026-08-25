"""Regression tests for the Phase 8A dataset foundation."""

from __future__ import annotations

import pandas as pd

from src.data.contract import CANONICAL_COLUMNS, FEATURE_REGISTRY
from src.data.pipeline import canonicalize, chronological_split, ingest, ingest_sqlite, profile_markdown, validate
from src.persistence.database import Database


def test_csv_json_and_canonical_contract(tmp_path):
    source = pd.DataFrame({"ticket_id": [1], "priority": ["High"], "created_hours": [1], "sla_breach": ["Yes"]})
    csv_path = tmp_path / "tickets.csv"; json_path = tmp_path / "tickets.json"
    source.to_csv(csv_path, index=False); source.to_json(json_path, orient="records")
    assert tuple(ingest(csv_path).columns) == CANONICAL_COLUMNS
    assert ingest(json_path).iloc[0]["actual_sla_breach"] == "Yes"


def test_sqlite_ingestion_validation_and_leakage(tmp_path):
    database = Database(tmp_path / "platform.db"); database.initialize()
    with database.session() as connection:
        connection.execute("INSERT INTO tickets(summary, priority, created_hours, status, source, created_at, updated_at) VALUES ('VPN', 'High', 2, 'Open', 'api', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')")
    report = validate(ingest_sqlite(database.path, "test"))
    assert report.valid and any("actual_sla_breach" in warning for warning in report.warnings)


def test_validation_chronological_split_and_profile():
    frame = canonicalize(pd.DataFrame({"ticket_id": [1, 2, 3, 4], "priority": ["High", "Medium", "Low", "High"], "created_hours": [1, 2, 3, 4], "created_timestamp": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]}), "test")
    train, validation, test = chronological_split(frame)
    report = validate(frame)
    assert len(train) + len(validation) + len(test) == 4
    assert "Rows: 4" in profile_markdown(frame, report)
    assert FEATURE_REGISTRY["actual_sla_breach"].prediction_time is False


def test_validation_rejects_invalid_priority_and_negative_duration():
    report = validate(canonicalize(pd.DataFrame({"priority": ["Urgent"], "created_hours": [-1]}), "test"))
    assert not report.valid and len(report.errors) == 2
