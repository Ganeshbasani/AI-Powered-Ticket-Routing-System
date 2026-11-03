# Dataset Contract

Schema version `1.1` provides one canonical representation for CSV, JSON,
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

`summary` and `description` are raw prediction-time text columns. They are kept
separate in storage and may be deterministically normalized and combined for a
future TF-IDF training pipeline. Text must be captured before prediction; text
that describes resolution, closure, a final team, or an observed SLA outcome is
leakage-prone even when it appears in a nominally permitted column. See the
[NLP feature foundation](nlp_pipeline.md) for the text contract and baseline.

Use `python -m src.cli validate-dataset data/tickets.csv`,
`python -m src.cli profile-dataset data/tickets.csv --report docs/dataset_profile.md`,
or `python -m src.cli assess-dataset data/tickets.csv`. The readiness assessment
reports separate SLA and routing decisions without fabricating a quality metric.

## Phase 8C Architecture Contracts

Schema `1.1` adds additive, nullable architecture fields for an authoritative
`initial_triage_team` target and SLA provenance. Legacy `assigned_team` remains
mutable platform state; it is not automatically converted to `initial_triage_team`
or `final_team`. Legacy `sla_breach` remains import-compatible as
`actual_sla_breach`, but carries no verified production SLA-policy provenance.

Production JIRA routing, team vocabulary, SLA policy, calendars, pause/extension
rules, and terminal outcome semantics are deliberately **UNCONFIGURED**. A
configured source profile must supply field/event mappings, vocabulary, and
provenance before it can produce authoritative targets. Ticket-scoped baseline
predictions persist immutable local-platform snapshots; external JIRA historical
provenance remains unconfigured.
See [Phase 8C architecture contracts](phase8c_architecture_contract.md).
