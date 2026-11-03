"""Regression tests for the Phase 8A dataset foundation."""

from __future__ import annotations

import pandas as pd

from src.cli import main
from src.data.contract import CANONICAL_COLUMNS, FEATURE_REGISTRY, prediction_time_columns
from src.data.nlp import build_tfidf_pipeline, combine_ticket_text, normalize_text, text_leakage_warnings
from src.data.pipeline import assess_readiness, canonicalize, chronological_split, ingest, ingest_sqlite, profile_markdown, validate
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


def test_text_normalization_and_combined_prediction_time_representation():
    assert normalize_text(None) == ""
    assert normalize_text(" <p>Ｆｉｘ!!!!!&nbsp;VPN</p> ") == "Fix!!! VPN"
    assert normalize_text("word " * 20, max_length=12) == "word word wo"
    record = {"summary": " VPN outage ", "description": " <b>Cannot connect</b> ", "actual_sla_breach": "Yes"}
    assert combine_ticket_text(record) == "VPN outage\n\nCannot connect"
    assert "actual_sla_breach" not in prediction_time_columns()


def test_tfidf_baseline_is_deterministic_and_unfitted_until_used():
    corpus = ["vpn outage", "email outage", "vpn password"]
    first = build_tfidf_pipeline(max_features=10, ngram_range=(1, 2)).fit_transform(corpus)
    second = build_tfidf_pipeline(max_features=10, ngram_range=(1, 2)).fit_transform(corpus)
    assert first.shape == second.shape
    assert (first.toarray() == second.toarray()).all()


def test_text_leakage_and_readiness_assessment_are_honest_for_prototype():
    prototype = canonicalize(
        pd.DataFrame({
            "priority": ["High", "Medium", "High"],
            "created_hours": [5, 2, 6],
            "summary": ["VPN resolved after SLA breach", "", ""],
            "sla_breach": ["Yes", "No", "Yes"],
            "assigned_team": ["L2", "L1", "L3"],
        }),
        "test",
    )
    assert text_leakage_warnings(prototype)
    assessment = assess_readiness(prototype)
    assert assessment.sla_status == "NOT READY"
    assert assessment.routing_status == "NOT READY"
    assert any("Only 3 rows" in reason for reason in assessment.sla_reasons)


def test_assessment_cli_reports_not_ready_for_small_prototype(tmp_path, monkeypatch, capsys):
    path = tmp_path / "tickets.csv"
    pd.DataFrame({"priority": ["High", "Medium", "High"], "created_hours": [5, 2, 6], "sla_breach": ["Yes", "No", "Yes"]}).to_csv(path, index=False)
    monkeypatch.setattr("sys.argv", ["cli", "assess-dataset", str(path)])
    main()
    output = capsys.readouterr().out
    assert '"sla_status": "NOT READY"' in output
    assert '"routing_status": "NOT READY"' in output
