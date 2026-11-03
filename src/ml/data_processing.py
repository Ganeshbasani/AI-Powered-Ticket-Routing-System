"""Data processing helpers for model training and prediction."""

from __future__ import annotations

import math
from os import PathLike

import pandas as pd

from src.config.settings import settings

FEATURE_COLUMNS = ("priority", "created_hours")
TARGET_COLUMN = "sla_breach"


def load_ticket_data(data_path: str | PathLike[str]) -> pd.DataFrame:
    df = pd.read_csv(data_path)
    return df


def validate_ticket_data(df: pd.DataFrame) -> pd.DataFrame:
    required_columns = [*FEATURE_COLUMNS, TARGET_COLUMN]
    if not all(column in df.columns for column in required_columns):
        raise ValueError("Data must include priority, created_hours, and sla_breach columns.")

    df = df.copy().drop_duplicates().reset_index(drop=True)
    df = df.dropna(subset=required_columns)
    df["created_hours"] = pd.to_numeric(df["created_hours"], errors="coerce")
    df = df.dropna(subset=["created_hours"])

    invalid_priorities = set(df["priority"]) - set(settings.priority_map)
    if invalid_priorities:
        raise ValueError(f"Unsupported priorities in training data: {sorted(invalid_priorities)}.")

    invalid_labels = set(df["sla_breach"]) - {"No", "Yes"}
    if invalid_labels:
        raise ValueError(f"Unsupported SLA breach labels in training data: {sorted(invalid_labels)}.")

    if not df["created_hours"].map(math.isfinite).all() or (df["created_hours"] < 0).any():
        raise ValueError("Training data must contain finite, non-negative created_hours values.")

    if df.empty:
        raise ValueError("No valid training records remain after validation.")

    return df


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return the raw prediction-time feature schema in a stable order."""
    return df.loc[:, FEATURE_COLUMNS].copy()


def prepare_labels(df: pd.DataFrame) -> pd.Series:
    return df[TARGET_COLUMN].map({"No": 0, "Yes": 1})
