"""Ticket data validation and feature preparation for triage models."""

from __future__ import annotations

import math
from os import PathLike

import pandas as pd

from src.config.settings import settings

TEXT_COLUMNS = ("summary", "description")
CATEGORICAL_COLUMNS = ("priority", "issue_type", "project", "component", "customer_tier", "channel")
NUMERIC_COLUMNS = ("created_hours",)
FEATURE_COLUMNS = (*TEXT_COLUMNS, *CATEGORICAL_COLUMNS, *NUMERIC_COLUMNS)
ROUTING_TARGET = "final_team"
SLA_TARGET = "sla_breach"


def load_ticket_data(data_path: str | PathLike[str]) -> pd.DataFrame:
    return pd.read_csv(data_path)


def validate_ticket_data(df: pd.DataFrame) -> pd.DataFrame:
    required_columns = [*FEATURE_COLUMNS, ROUTING_TARGET, SLA_TARGET]
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Data is missing required columns: {', '.join(missing)}.")

    frame = df.copy().drop_duplicates().reset_index(drop=True)
    for column in TEXT_COLUMNS + CATEGORICAL_COLUMNS + (ROUTING_TARGET, SLA_TARGET):
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    frame["created_hours"] = pd.to_numeric(frame["created_hours"], errors="coerce")
    frame = frame.dropna(subset=["created_hours"]).reset_index(drop=True)

    invalid_priorities = set(frame["priority"]) - set(settings.priority_map)
    if invalid_priorities:
        raise ValueError(f"Unsupported priorities in training data: {sorted(invalid_priorities)}.")

    invalid_labels = set(frame[SLA_TARGET]) - {"No", "Yes"}
    if invalid_labels:
        raise ValueError(f"Unsupported SLA breach labels in training data: {sorted(invalid_labels)}.")

    if frame[ROUTING_TARGET].eq("").any():
        raise ValueError("Training data must contain a final_team routing label for every row.")
    if frame["summary"].eq("").any():
        raise ValueError("Training data must contain a non-empty summary for every row.")
    if not frame["created_hours"].map(math.isfinite).all() or (frame["created_hours"] < 0).any():
        raise ValueError("Training data must contain finite, non-negative created_hours values.")
    if frame.empty:
        raise ValueError("No valid training records remain after validation.")

    return frame


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return the prediction-time schema in a stable order."""
    features = df.loc[:, FEATURE_COLUMNS].copy()
    features["summary"] = features["summary"].fillna("").astype(str)
    features["description"] = features["description"].fillna("").astype(str)
    return features


def prepare_routing_labels(df: pd.DataFrame) -> pd.Series:
    return df[ROUTING_TARGET].astype(str)


def prepare_sla_labels(df: pd.DataFrame) -> pd.Series:
    return df[SLA_TARGET].map({"No": 0, "Yes": 1})
