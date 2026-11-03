"""Deterministic, prediction-time-safe text preparation utilities.

The functions here intentionally prepare text only. They do not fit a model or
change the serialized production prediction pipeline.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Mapping

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline

TEXT_COLUMNS = ("summary", "description")
_HTML_TAG = re.compile(r"<[^>]*>")
_REPEATED_CHARACTER = re.compile(r"(.)\1{4,}")
_WHITESPACE = re.compile(r"\s+")
_TEXT_LEAKAGE = re.compile(
    r"\b(?:actual\s+sla|sla\s+(?:breach|met)|resolved|resolution|closed|final\s+(?:status|team)|assigned\s+to)\b",
    re.IGNORECASE,
)


def normalize_text(value: object | None, max_length: int = 10_000) -> str:
    """Normalize user-authored ticket text without stripping useful punctuation."""
    if value is None or pd.isna(value):
        return ""
    if max_length < 1:
        raise ValueError("max_length must be positive.")
    text = unicodedata.normalize("NFKC", html.unescape(str(value)))
    text = _HTML_TAG.sub(" ", text)
    text = _REPEATED_CHARACTER.sub(lambda match: match.group(1) * 3, text)
    return _WHITESPACE.sub(" ", text).strip()[:max_length]


def combine_ticket_text(record: Mapping[str, object], max_length: int = 10_000) -> str:
    """Combine only prediction-time text fields; outcome fields are never read."""
    parts = [normalize_text(record.get(column), max_length=max_length) for column in TEXT_COLUMNS]
    return "\n\n".join(part for part in parts if part)[:max_length]


def build_tfidf_pipeline(
    *, max_features: int = 5_000, min_document_frequency: int = 1, ngram_range: tuple[int, int] = (1, 2)
) -> Pipeline:
    """Create an unfitted, deterministic traditional NLP baseline pipeline."""
    if max_features < 1 or min_document_frequency < 1 or ngram_range[0] < 1 or ngram_range[0] > ngram_range[1]:
        raise ValueError("Invalid TF-IDF configuration.")
    return Pipeline(
        [("tfidf", TfidfVectorizer(max_features=max_features, min_df=min_document_frequency, ngram_range=ngram_range, lowercase=True))]
    )


def text_leakage_warnings(frame: pd.DataFrame) -> list[str]:
    """Report suspicious outcome language in raw text without altering records."""
    warnings: list[str] = []
    for column in TEXT_COLUMNS:
        if column not in frame:
            continue
        matches = frame[column].fillna("").astype(str).str.contains(_TEXT_LEAKAGE, na=False)
        if int(matches.sum()):
            warnings.append(
                f"{column} contains outcome-like language in {int(matches.sum())} row(s); review for post-resolution leakage."
            )
    return warnings
