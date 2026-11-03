"""Synthetic pipeline and candidate-artifact regression tests."""

from __future__ import annotations

import json

import pytest

from src.cli import main
from src.data.nlp import text_leakage_warnings
from src.data.pipeline import assess_readiness, validate
from src.data.synthetic import generate_synthetic_dataset, write_synthetic_dataset
from src.ml.candidates import train_candidate_models


def test_synthetic_generation_is_deterministic_and_leakage_safe():
    first, first_manifest = generate_synthetic_dataset(120, seed=7)
    second, second_manifest = generate_synthetic_dataset(120, seed=7)
    different, _ = generate_synthetic_dataset(120, seed=8)
    assert first.equals(second)
    assert first_manifest.logical_checksum_sha256 == second_manifest.logical_checksum_sha256
    assert not first.equals(different)
    assert not text_leakage_warnings(first)
    assert validate(first).valid
    readiness = assess_readiness(first)
    assert readiness.sla_status == "READY WITH WARNINGS"
    assert readiness.routing_status == "READY WITH WARNINGS"
    assert first["initial_triage_team"].nunique() == 3


def test_synthetic_outputs_are_isolated_and_candidate_artifacts_are_versioned(tmp_path):
    data_path, manifest_path, artifacts = tmp_path / "medium.csv", tmp_path / "medium.manifest.json", tmp_path / "candidates"
    manifest = write_synthetic_dataset(data_path, manifest_path, record_count=180, seed=9)
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["logical_checksum_sha256"] == manifest.logical_checksum_sha256
    result = train_candidate_models(data_path, manifest_path, artifacts)
    assert set(result) == {"routing", "sla"}
    for details in result.values():
        assert len(details["artifact_sha256"]) == 64
        assert "Synthetic evaluation" in details["evaluation"]["warning"]


def test_synthetic_writer_refuses_legacy_dataset_path(tmp_path):
    with pytest.raises(ValueError, match="must not overwrite"):
        write_synthetic_dataset(tmp_path / "tickets.csv", tmp_path / "manifest.json", record_count=1)


def test_synthetic_writer_refuses_existing_versioned_output(tmp_path):
    data_path, manifest_path = tmp_path / "synthetic-v1.csv", tmp_path / "synthetic-v1.manifest.json"
    write_synthetic_dataset(data_path, manifest_path, record_count=10)
    with pytest.raises(ValueError, match="already exists"):
        write_synthetic_dataset(data_path, manifest_path, record_count=10)


def test_synthetic_cli_assessment_preserves_origin_warning(tmp_path, monkeypatch, capsys):
    data_path, manifest_path = tmp_path / "synthetic.csv", tmp_path / "synthetic.manifest.json"
    write_synthetic_dataset(data_path, manifest_path, record_count=120)
    monkeypatch.setattr("sys.argv", ["cli", "assess-dataset", str(data_path)])
    main()
    output = capsys.readouterr().out
    assert '"sla_status": "READY WITH WARNINGS"' in output
