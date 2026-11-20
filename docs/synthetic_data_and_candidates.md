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

When both versioned artifacts and their checksum sidecars exist, ticket
creation and manual assessments run the candidates and persist their routing
and SLA outputs, confidence/margin review flags, feature snapshot, artifact
hash, evaluation, and training origin in `ml_assessments`. Candidate results
remain separate from policy-based SLA history. The assigned support team is
not changed automatically. The platform does not currently store issue type,
project, or component, so those structured candidate fields are passed as
`Unknown` and ignored by the fitted one-hot encoder. Artifacts are checked for
checksum, schema, version, and data origin before inference. Low confidence or
small class margins are marked for human review.

The bundled candidate scores are from synthetic development models. They are
not calibrated probabilities, routing guarantees, or evidence of real-world
performance. The dashboard and ticket details keep this warning visible. The
legacy three-row Random Forest artifact is retired and is not used by runtime.
For observed-data training requirements, timestamp checks, holdout rules, and
fail-closed behavior, see [model training and safeguards](model_training.md).

## Generator Contract

The generator uses a fixed seed, fixed UTC anchor, deterministic IDs and
ordering, latent scenario families, canonical schema order, and a SHA-256
logical-content checksum. It creates pre-ticket fields and safe text first, then
derives routing and SLA labels from latent workload rules. Generated text does
not use outcome terms such as breach, closure, resolution, or final team.

## Candidate Evaluation

Routing and SLA candidates use versioned structured features plus deterministic
TF-IDF text. They are chronologically split at 70/15/15. SLA evaluation uses
prediction timestamps and requires the outcome to occur after the scoring time.
Artifacts save model version, feature-schema version, manifest checksum,
generator/rule versions, random seed, environment metadata, and an artifact
SHA-256 sidecar. Reported metrics are synthetic development evidence, not
production evidence.

## JSM Reference Profile

`jira_service_management_cloud_reference` is intentionally unconfigured. Jira
Service Management supports project-specific SLA goals, calendars, and start,
pause, and stop conditions; a real source profile must therefore supply the
organization's approved field IDs, routing vocabulary, SLA metric/policy, and
privacy controls before historical extraction. See Atlassian's
[SLA configuration guidance](https://support.atlassian.com/jira-service-management-cloud/docs/create-service-level-agreements-slas/)
and [SLA JQL state functions](https://support.atlassian.com/jira-service-management-cloud/docs/jql-fields/).
