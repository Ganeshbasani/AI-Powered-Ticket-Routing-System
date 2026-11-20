# Ticket model training and safeguards

Ticket creation runs the text-based routing and SLA classifiers when a
checksum-verified model pair is available. Results and model provenance are
stored in `ml_assessments`. A team recommendation never changes
`assigned_team`; a low score or narrow class margin is marked for human review.

The packaged `8c-candidate-3` models are trained on synthetic development data.
They exercise the live inference path, but their scores are explicitly labeled
synthetic and uncalibrated. They are not evidence of real-world accuracy. The
normal SLA status remains a separate, transparent priority/age policy result.

## Training from observed history

The current bundled CSV has only three rows and cannot pass the observed-data
training gate. Do not turn generated demo records or mutable current team
assignments into training labels. Supply permissioned records with the actual
prediction-time fields, outcomes, and source event evidence before training.

The CSV must contain `summary`, `description`, `priority`, `created_hours`,
`created_timestamp`, `prediction_timestamp`, `initial_triage_team`,
`initial_triage_event_id`, `initial_triage_decided_at`,
`initial_triage_decision_source`, `actual_sla_breach`, `sla_outcome_state`,
`sla_policy_id`, `sla_policy_version`, `sla_source_event_id`, and
`sla_outcome_observed_at`, `sla_pause_seconds`, and `sla_extension_seconds`.
The current model gate accepts only unpaused, unextended clocks. Ages must agree
with timestamps within 15 minutes; the prediction timestamp must precede the
observed SLA outcome. The data needs
at least 200 rows, two supported classes, sufficient per-class train/test
support, and a chronological holdout. Both models must reach at least 0.50 F1
on the final chronological holdout or no artifacts are written.

The adjacent JSON manifest must attest the source and exact CSV checksum:

```json
{
  "record_origin": "observed",
  "source_system": "your-ticket-system",
  "extracted_at": "2026-01-15T12:00:00+00:00",
  "dataset_sha256": "<sha256 of the exact CSV file>",
  "source_profile": {
    "configured": true,
    "name": "approved-source-profile"
  }
}
```

Train only after validating the source mapping and label provenance:

```powershell
python -m src.cli train-observed path/to/observed_tickets.csv --manifest path/to/observed_tickets.manifest.json
```

This writes a versioned routing/SLA pair into `ml_model/verified`. The runtime
prefers the observed pair only when both artifacts and checksum manifests
validate. A partial, corrupt, low-quality, or mismatched pair fails closed;
ticket creation continues with a clear unavailable result and does not assign a
team. Holdout metrics describe the supplied historical sample only and do not
guarantee future performance.

## Runtime age and alerts

Tickets retain an initial age offset plus a timestamp reference. API reads,
policy calculations, ML inputs, and dashboard alerts advance age from that
reference. The dashboard polls current alert counts every 30 seconds. The
configured policy is still a clock-time estimate: business calendars, SLA
pauses, holidays, and extensions require organization-specific rules that are
not yet configured.
