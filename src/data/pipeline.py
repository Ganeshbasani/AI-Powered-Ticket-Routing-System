"""Unified canonical data ingestion and non-destructive quality reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

import pandas as pd

from src.config.settings import settings
from src.data.contract import CANONICAL_COLUMNS, FEATURE_REGISTRY, OUTCOME_FIELDS, PREDICTION_FIELDS, SCHEMA_VERSION


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


def canonicalize(frame: pd.DataFrame, source: str, dataset_version: str = "unversioned") -> pd.DataFrame:
    data = frame.copy()
    aliases = {"sla_breach": "actual_sla_breach", "assigned_team": "final_team", "status": "final_status"}
    for old, new in aliases.items():
        if old in data and new not in data: data[new] = data[old]
    for column in CANONICAL_COLUMNS:
        if column not in data: data[column] = pd.NA
    data["dataset_version"] = dataset_version
    data["ingestion_source"] = source
    data["imported_at"] = datetime.now(UTC).isoformat()
    return data.loc[:, CANONICAL_COLUMNS]


def ingest(path: Path | str, source: str | None = None, dataset_version: str = "unversioned") -> pd.DataFrame:
    path = Path(path); suffix = path.suffix.lower(); source = source or suffix.lstrip(".")
    if suffix == ".csv": frame = pd.read_csv(path)
    elif suffix == ".json": frame = pd.read_json(path)
    else: raise ValueError("Only CSV and JSON dataset files are supported.")
    return canonicalize(frame, source, dataset_version)


def ingest_sqlite(path: Path | str, dataset_version: str = "unversioned") -> pd.DataFrame:
    with sqlite3.connect(path) as connection:
        frame = pd.read_sql_query("SELECT id AS ticket_id, jira_issue_key, summary, description, priority, created_hours, source, actual_sla_breach, created_at AS created_timestamp, status AS final_status, assigned_team AS final_team FROM tickets", connection)
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
    return report


def leakage_warnings(frame: pd.DataFrame) -> list[str]:
    warnings = []
    for column in frame.columns:
        normalized = column.lower()
        if column in OUTCOME_FIELDS: warnings.append(f"{column} is outcome-only and must not be a prediction feature.")
        elif column in {"ticket_id", "jira_issue_key"}: warnings.append(f"{column} is an identifier and may enable memorization.")
        elif any(word in normalized for word in ("resolution", "final_", "closed", "breach")): warnings.append(f"{column} appears leakage-prone; review prediction-time availability.")
    return warnings


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
