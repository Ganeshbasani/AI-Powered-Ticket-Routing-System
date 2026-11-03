"""Unified canonical data ingestion and non-destructive quality reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

import pandas as pd

from src.config.settings import settings
from src.data.contract import CANONICAL_COLUMNS, FEATURE_REGISTRY, OUTCOME_FIELDS, PREDICTION_FIELDS, PREDICTION_TARGET_FIELDS, SCHEMA_VERSION
from src.data.nlp import text_leakage_warnings


@dataclass
class ValidationReport:
    row_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_rows: int = 0
    missing_values: dict[str, int] = field(default_factory=dict)

    @property
    def valid(self) -> bool: return not self.errors

    def as_dict(self) -> dict: return asdict(self)


@dataclass
class DatasetReadinessReport:
    """Evidence-based readiness assessment, not a claim of model quality."""

    row_count: int
    timestamp_coverage: int
    text_coverage: dict[str, int]
    target_distribution: dict[str, int]
    routing_label_distribution: dict[str, int]
    missing_values: dict[str, int]
    duplicate_rows: int
    leakage_warnings: list[str]
    sla_status: str
    sla_reasons: list[str]
    routing_status: str
    routing_reasons: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def canonicalize(frame: pd.DataFrame, source: str, dataset_version: str = "unversioned") -> pd.DataFrame:
    data = frame.copy()
    # Legacy SLA labels remain import-compatible. Assignment and status remain
    # mutable until an explicit source profile proves authoritative semantics.
    aliases = {"sla_breach": "actual_sla_breach"}
    for old, new in aliases.items():
        if old in data and new not in data: data[new] = data[old]
    for column in CANONICAL_COLUMNS:
        if column not in data: data[column] = pd.NA
    # Preserve producer lineage (for example synthetic manifests) on re-ingest;
    # legacy files receive the importer metadata as before.
    data["dataset_version"] = data["dataset_version"].fillna(dataset_version)
    data["ingestion_source"] = data["ingestion_source"].fillna(source)
    data["imported_at"] = data["imported_at"].fillna(datetime.now(UTC).isoformat())
    return data.loc[:, CANONICAL_COLUMNS]


def ingest(path: Path | str, source: str | None = None, dataset_version: str = "unversioned") -> pd.DataFrame:
    path = Path(path); suffix = path.suffix.lower(); source = source or suffix.lstrip(".")
    if suffix == ".csv": frame = pd.read_csv(path)
    elif suffix == ".json": frame = pd.read_json(path)
    else: raise ValueError("Only CSV and JSON dataset files are supported.")
    return canonicalize(frame, source, dataset_version)


def ingest_sqlite(path: Path | str, dataset_version: str = "unversioned") -> pd.DataFrame:
    with sqlite3.connect(path) as connection:
        frame = pd.read_sql_query("SELECT id AS ticket_id, jira_issue_key, summary, description, priority, created_hours, source, actual_sla_breach, created_at AS created_timestamp, status, assigned_team FROM tickets", connection)
    return canonicalize(frame, "sqlite", dataset_version)


def validate(frame: pd.DataFrame) -> ValidationReport:
    report = ValidationReport(row_count=len(frame))
    report.missing_values = {column: int(frame[column].isna().sum()) for column in frame.columns if frame[column].isna().any()}
    required = ("priority", "created_hours")
    for column in required:
        if column not in frame: report.errors.append(f"Missing required column: {column}.")
    if report.errors: return report
    invalid_priority = set(frame["priority"].dropna()) - set(settings.priority_map)
    if invalid_priority: report.errors.append(f"Invalid priorities: {sorted(invalid_priority)}.")
    ages = pd.to_numeric(frame["created_hours"], errors="coerce")
    if ages.isna().any() or (ages < 0).any(): report.errors.append("created_hours must be finite non-negative numbers.")
    for label in ("actual_sla_breach",):
        if label in frame:
            invalid = set(frame[label].dropna()) - {"Yes", "No"}
            if invalid: report.errors.append(f"Invalid {label} values: {sorted(invalid)}.")
    report.duplicate_rows = int(frame.duplicated().sum())
    if report.duplicate_rows: report.warnings.append(f"Found {report.duplicate_rows} exact duplicate rows.")
    for key in ("ticket_id", "jira_issue_key"):
        if key in frame and frame[key].notna().any() and frame.loc[frame[key].notna(), key].duplicated().any(): report.warnings.append(f"Duplicate {key} values detected.")
    for column in ("created_timestamp", "resolution_timestamp"):
        if column in frame and frame[column].notna().any() and pd.to_datetime(frame[column], errors="coerce", utc=True).isna().any(): report.warnings.append(f"Malformed {column} values detected.")
    report.warnings.extend(leakage_warnings(frame))
    report.warnings.extend(text_leakage_warnings(frame))
    return report


def leakage_warnings(frame: pd.DataFrame) -> list[str]:
    warnings = []
    for column in frame.columns:
        normalized = column.lower()
        if column in PREDICTION_TARGET_FIELDS: warnings.append(f"{column} is a prediction target and must not be a prediction feature.")
        elif column in OUTCOME_FIELDS: warnings.append(f"{column} is outcome-only and must not be a prediction feature.")
        elif column in {"ticket_id", "jira_issue_key"}: warnings.append(f"{column} is an identifier and may enable memorization.")
        elif any(word in normalized for word in ("resolution", "final_", "closed", "breach")): warnings.append(f"{column} appears leakage-prone; review prediction-time availability.")
    return warnings


def assess_readiness(frame: pd.DataFrame, minimum_rows: int = 100) -> DatasetReadinessReport:
    """Assess whether a dataset has basic evidence to begin SLA/routing ML work.

    Passing this heuristic is not a quality or production-readiness guarantee.
    """
    if minimum_rows < 1:
        raise ValueError("minimum_rows must be positive.")
    report = validate(frame)
    coverage = {
        column: int(frame[column].fillna("").astype(str).str.strip().ne("").sum())
        for column in ("summary", "description")
        if column in frame
    }
    timestamp_coverage = int(frame["created_timestamp"].notna().sum()) if "created_timestamp" in frame else 0
    target_distribution = _distribution(frame, "actual_sla_breach")
    routing_distribution = _distribution(frame, "initial_triage_team")
    shared_reasons = []
    if len(frame) < minimum_rows:
        shared_reasons.append(f"Only {len(frame)} rows are available; at least {minimum_rows} are required for an initial assessment.")
    if timestamp_coverage == 0:
        shared_reasons.append("No prediction-time creation timestamps are available for chronological evaluation.")
    text_total = sum(coverage.values())
    sla_reasons = list(shared_reasons)
    if sum(target_distribution.values()) == 0:
        sla_reasons.append("No observed actual_sla_breach labels are available.")
    elif len(target_distribution) < 2:
        sla_reasons.append("SLA labels contain fewer than two classes.")
    routing_reasons = list(shared_reasons)
    if text_total == 0:
        routing_reasons.append("No summary or description text is available for text-based routing.")
    if sum(routing_distribution.values()) == 0:
        routing_reasons.append("No authoritative initial_triage_team labels are available for routing training.")
    elif len(routing_distribution) < 2:
        routing_reasons.append("Routing labels contain fewer than two teams.")
    synthetic = "ingestion_source" in frame and frame["ingestion_source"].fillna("").eq("synthetic_pipeline").all()
    if synthetic:
        warning = "Synthetic records validate pipeline structure only; they are not production ML evidence."
        if not sla_reasons:
            sla_reasons.append(warning)
        if not routing_reasons:
            routing_reasons.append(warning)
    return DatasetReadinessReport(
        row_count=len(frame),
        timestamp_coverage=timestamp_coverage,
        text_coverage=coverage,
        target_distribution=target_distribution,
        routing_label_distribution=routing_distribution,
        missing_values=report.missing_values,
        duplicate_rows=report.duplicate_rows,
        leakage_warnings=report.warnings,
        sla_status="READY WITH WARNINGS" if synthetic and len(sla_reasons) == 1 else ("READY" if not sla_reasons else "NOT READY"),
        sla_reasons=sla_reasons,
        routing_status="READY WITH WARNINGS" if synthetic and len(routing_reasons) == 1 else ("READY" if not routing_reasons else "NOT READY"),
        routing_reasons=routing_reasons,
    )


def _distribution(frame: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in frame:
        return {}
    values = frame[column].dropna().astype(str).str.strip()
    values = values[values.ne("")]
    return {str(key): int(value) for key, value in values.value_counts().items()}


def chronological_split(frame: pd.DataFrame, timestamp_column: str = "created_timestamp", train_fraction: float = 0.7, validation_fraction: float = 0.15) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if timestamp_column not in frame or frame[timestamp_column].isna().all(): raise ValueError("Chronological splitting requires timestamp coverage.")
    ordered = frame.assign(_time=pd.to_datetime(frame[timestamp_column], utc=True, errors="raise")).sort_values("_time").drop(columns="_time")
    train_end, validation_end = int(len(ordered) * train_fraction), int(len(ordered) * (train_fraction + validation_fraction))
    return ordered.iloc[:train_end], ordered.iloc[train_end:validation_end], ordered.iloc[validation_end:]


def profile_markdown(frame: pd.DataFrame, report: ValidationReport) -> str:
    distribution = lambda column: frame[column].value_counts(dropna=False).to_dict() if column in frame else {}
    text_available = {column: int(frame[column].fillna("").astype(str).str.strip().ne("").sum()) for column in ("summary", "description") if column in frame}
    warning_lines = [f"- {warning}" for warning in report.warnings] or ["- None"]
    return "\n".join(["# Dataset Profile", "", f"- Rows: {len(frame)}", f"- Schema version: {SCHEMA_VERSION}", f"- Validation status: {'valid' if report.valid else 'invalid'}", f"- Missing values: {report.missing_values}", f"- Exact duplicates: {report.duplicate_rows}", f"- Priority distribution: {distribution('priority')}", f"- Issue-type distribution: {distribution('issue_type')}", f"- SLA outcome distribution: {distribution('actual_sla_breach')}", f"- Text availability: {text_available}", f"- Timestamp coverage: {int(frame['created_timestamp'].notna().sum()) if 'created_timestamp' in frame else 0}", "", "## Leakage Warnings", *warning_lines, "", "## Limitation", "The bundled prototype contains 3 records and cannot support meaningful ML evaluation."])
