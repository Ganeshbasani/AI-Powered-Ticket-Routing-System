# Dataset Contract

Schema version `1.0` provides one canonical representation for CSV, JSON,
SQLite ticket exports, and mock-JIRA exports. Prediction-time columns are
`priority`, `created_hours`, `issue_type`, `project`, `component`, `summary`,
`description`, and `created_timestamp`. Outcome-only columns include
`actual_sla_breach`, resolution fields, `final_status`, and `final_team`; they
must never be supplied to prediction or training features.

Metadata records `dataset_version`, `ingestion_source`, and `imported_at`.
Identifiers are preserved for lineage but flagged as leakage-prone because they
can enable memorization. Validation reports errors and warnings without silently
deleting input rows. When timestamp coverage exists, use chronological splits;
the bundled prototype has no timestamps and cannot be evaluated meaningfully.

Use `python -m src.cli validate-dataset data/tickets.csv` or
`python -m src.cli profile-dataset data/tickets.csv --report docs/dataset_profile.md`.
