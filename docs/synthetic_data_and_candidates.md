# Synthetic Data And Candidate Models

Phase 8C creates deterministic **synthetic pipeline data** only. It is not
observed production data and must never be used to claim production routing or
SLA performance.

## Commands

Generate an isolated dataset and manifest:

```bash
python -m src.cli generate-synthetic data/synthetic/medium.csv --size medium --seed 20260826
```

Train isolated candidate artifacts from that synthetic manifest:

```bash
python -m src.cli train-candidates data/synthetic/medium.csv --artifacts ml_model/candidates
```

The legacy `data/tickets.csv` path is refused as a synthetic output target.
Candidate artifacts are saved under `ml_model/candidates`; the production
`ml_model/sla_model.joblib` artifact and `/predict` are never replaced.

## Generator Contract

The generator uses a fixed seed, fixed UTC anchor, deterministic IDs and
ordering, latent scenario families, canonical schema order, and a SHA-256
logical-content checksum. It creates pre-ticket fields and safe text first, then
derives routing and SLA labels from latent workload rules. Generated text does
not use outcome terms such as breach, closure, resolution, or final team.

## Candidate Evaluation

Routing and SLA candidates use versioned structured features plus deterministic
TF-IDF text. They are chronologically split at 70/15/15 and save model version,
feature-schema version, manifest checksum, generator/rule versions, random seed,
environment metadata, and a separate artifact SHA-256 sidecar. Reported metrics
are explicitly synthetic development evidence, not production evidence.

## JSM Reference Profile

`jira_service_management_cloud_reference` is intentionally unconfigured. Jira
Service Management supports project-specific SLA goals, calendars, and start,
pause, and stop conditions; a real source profile must therefore supply the
organization's approved field IDs, routing vocabulary, SLA metric/policy, and
privacy controls before historical extraction. See Atlassian's
[SLA configuration guidance](https://support.atlassian.com/jira-service-management-cloud/docs/create-service-level-agreements-slas/)
and [SLA JQL state functions](https://support.atlassian.com/jira-service-management-cloud/docs/jql-fields/).
