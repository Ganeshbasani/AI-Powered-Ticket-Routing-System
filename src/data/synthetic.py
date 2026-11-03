"""Deterministic synthetic data for pipeline testing, never production evidence."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from src.data.contract import CANONICAL_COLUMNS, SCHEMA_VERSION

GENERATOR_VERSION = "8c-synthetic-2"
RULE_SET_VERSION = "8c-latent-scenarios-1"
SYNTHETIC_SOURCE = "synthetic_pipeline"
SIZE_PRESETS = {"small": 120, "medium": 1_200, "large": 5_000}
_TEXT = {
    "network": [("Connection drops during work", "The workstation loses access while using the internal service."), ("VPN session cannot start", "A remote worker cannot establish the normal secure connection.")],
    "identity": [("Portal sign-in is unavailable", "The account cannot complete the usual sign-in flow."), ("Access request needs review", "A user needs access to a standard internal application.")],
    "workplace": [("Device setup request", "A laptop needs a standard workplace configuration."), ("Email client is not syncing", "The desktop mail application is not receiving new messages.")],
}
_SCENARIOS = (
    ("network", "NET", "connectivity", "Network"),
    ("identity", "IAM", "access", "Identity"),
    ("workplace", "WKP", "endpoint", "Workplace"),
)


@dataclass(frozen=True)
class SyntheticManifest:
    schema_version: str
    generator_version: str
    rule_set_version: str
    random_seed: int
    fixed_time_anchor: str
    timezone: str
    record_count: int
    scenario_families: list[str]
    canonical_column_order: list[str]
    logical_checksum_sha256: str
    synthetic: bool
    distributions: dict[str, dict[str, int]]
    generation_configuration: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def generate_synthetic_dataset(
    record_count: int = SIZE_PRESETS["medium"], *, seed: int = 20260826,
    fixed_time_anchor: str = "2024-01-01T00:00:00+00:00",
) -> tuple[pd.DataFrame, SyntheticManifest]:
    """Generate latent scenarios first, then independent text and documented targets."""
    if record_count < 1:
        raise ValueError("record_count must be positive.")
    anchor = _parse_anchor(fixed_time_anchor)
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    for index in range(record_count):
        family, project, component, preferred_team = _SCENARIOS[index % len(_SCENARIOS)]
        # Latent workload drives targets; the selected text template does not.
        workload = rng.randint(1, 10)
        priority = "High" if workload >= 8 else "Medium" if workload >= 4 else "Low"
        created_at = anchor + timedelta(hours=index * 3 + rng.randint(0, 2))
        created_hours = float(rng.randint(1, 72))
        summary, description = rng.choice(_TEXT[family])
        # Controlled noise prevents labels from being a direct encoding of one
        # structured feature or a text-template family.
        team = preferred_team if rng.random() < 0.72 else rng.choice([item[3] for item in _SCENARIOS if item[3] != preferred_team])
        sla_yes = workload + rng.randint(-2, 3) >= 8
        deadline_at = created_at + timedelta(hours=created_hours + rng.randint(12, 36))
        outcome_at = deadline_at + timedelta(hours=rng.randint(1, 12)) if sla_yes else deadline_at - timedelta(hours=rng.randint(1, 8))
        rows.append({
            "ticket_id": f"SYN-{index + 1:06d}", "jira_issue_key": pd.NA,
            "priority": priority, "created_hours": created_hours, "issue_type": "Incident" if family == "network" else "Service Request",
            "project": project, "component": component, "summary": summary, "description": description,
            "created_timestamp": created_at.isoformat(), "initial_triage_team": team,
            "initial_triage_decided_at": created_at.isoformat(), "initial_triage_event_id": f"synthetic-routing-{index + 1}",
            "initial_triage_decision_source": "automation", "initial_triage_source_system": SYNTHETIC_SOURCE,
            "initial_triage_is_automated": True, "assigned_team": pd.NA, "status": "open", "updated_at": created_at.isoformat(),
            "actual_sla_breach": "Yes" if sla_yes else "No", "sla_outcome_state": "observed",
            "sla_clock_started_at": created_at.isoformat(), "sla_deadline_at": deadline_at.isoformat(),
            "sla_breach_observed_at": outcome_at.isoformat() if sla_yes else pd.NA,
            "sla_outcome_observed_at": outcome_at.isoformat(), "sla_policy_id": "synthetic-policy", "sla_policy_version": RULE_SET_VERSION,
            "sla_pause_seconds": 0, "sla_extension_seconds": 0, "sla_source_event_id": f"synthetic-sla-{index + 1}",
            "resolution_timestamp": outcome_at.isoformat(), "resolution_time": created_hours + rng.randint(1, 24),
            "final_status": "completed", "final_team": team, "dataset_version": SCHEMA_VERSION,
            "ingestion_source": SYNTHETIC_SOURCE, "imported_at": anchor.isoformat(),
        })
    frame = pd.DataFrame(rows).loc[:, CANONICAL_COLUMNS]
    serialized = frame.fillna("").to_csv(index=False, lineterminator="\n")
    manifest = SyntheticManifest(
        schema_version=SCHEMA_VERSION, generator_version=GENERATOR_VERSION, rule_set_version=RULE_SET_VERSION,
        random_seed=seed, fixed_time_anchor=anchor.isoformat(), timezone="UTC", record_count=record_count,
        scenario_families=sorted(_TEXT), canonical_column_order=list(CANONICAL_COLUMNS),
        logical_checksum_sha256=hashlib.sha256(serialized.encode("utf-8")).hexdigest(), synthetic=True,
        distributions={
            "actual_sla_breach": _distribution(frame, "actual_sla_breach"),
            "initial_triage_team": _distribution(frame, "initial_triage_team"),
            "priority": _distribution(frame, "priority"),
        },
        generation_configuration={"record_count": record_count, "seed": seed, "fixed_time_anchor": anchor.isoformat()},
    )
    return frame, manifest


def write_synthetic_dataset(data_path: Path | str, manifest_path: Path | str, **configuration: object) -> SyntheticManifest:
    """Write a standalone synthetic dataset and manifest, never the legacy dataset."""
    data_path, manifest_path = Path(data_path), Path(manifest_path)
    if data_path.name == "tickets.csv":
        raise ValueError("Synthetic output must not overwrite the legacy tickets.csv dataset.")
    if data_path.exists() or manifest_path.exists():
        raise ValueError("Synthetic output already exists; choose a versioned output path.")
    frame, manifest = generate_synthetic_dataset(**configuration)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(data_path, index=False, lineterminator="\n")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _distribution(frame: pd.DataFrame, column: str) -> dict[str, int]:
    return {str(key): int(value) for key, value in frame[column].value_counts().sort_index().items()}


def _parse_anchor(value: str) -> datetime:
    anchor = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if anchor.tzinfo is None:
        raise ValueError("fixed_time_anchor must include a timezone.")
    return anchor.astimezone(UTC)
