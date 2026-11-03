# Phase 8C Architecture Contracts

Phase 8C adds contracts and validation interfaces only. It does not create
synthetic data, alter the legacy dataset, retrain a model, persist snapshots, or
change `/predict`.

## Canonical Field Safety

`initial_triage_team` is a future prediction target only when an approved source
profile proves the first authoritative routing decision. `assigned_team` and
`status` are mutable platform state. `final_team`, `final_status`, resolution
fields, and SLA observation timestamps are post-resolution outcomes. The
observed SLA label, `actual_sla_breach`, is a target only. None may be prediction
features.

The legacy `sla_breach` import alias remains supported for backward
compatibility, but it is not proof of an authoritative production SLA policy.
The legacy `assigned_team` value is preserved as mutable state and is never
silently promoted to an initial or final routing target.

## Source Profiles And Provenance

`UNCONFIGURED_SOURCE_PROFILE` intentionally refuses routing-target extraction.
A future profile must provide source field IDs, source event IDs, event and
extraction timestamps, an approved team vocabulary, actor identity where
available, decision source, source ticket version, and observed/synthetic
origin. It also declares mappings independently for routing, SLA, and text
fields, plus timestamp meaning. No JIRA field or team vocabulary is configured
by this repository.

## Immutable Snapshots

`PredictionSnapshot` is a frozen validation contract. It requires ticket and
source-version identifiers, scoring time, canonical serialized feature values,
source event IDs, model/schema versions, artifact hash, text-normalization
version, source system, origin, and synthetic-generator lineage when relevant.
It rejects targets, outcomes, identifiers, and unproven mutable state as model
features. Ticket-scoped baseline predictions now persist one immutable snapshot
in SQLite. The snapshot uses local platform ticket-version evidence; it does not
claim authoritative external JIRA event provenance.

## Unresolved Business Semantics

The project owner must still approve the real JIRA routing field/event, routing
vocabulary, SLA clock and policy, pauses/extensions, terminal non-breach event,
and ticket-text retention policy before a production source profile or dataset
can be created.

## Candidate Development Boundary

Synthetic records and candidate artifacts are isolated from the baseline model.
The candidate workflow is an explicit CLI operation and cannot automatically
promote, load, or replace the production artifact. A real JSM source profile
remains unconfigured because SLA states depend on project-specific goals,
calendars, and start/pause/stop conditions.
