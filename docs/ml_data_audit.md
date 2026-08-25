# ML Data and Leakage Audit

## Target and Prediction Point

The current target is the `sla_breach` dataset label: `Yes` is encoded as 1 and
`No` as 0. Predictions use ticket priority and the elapsed `created_hours` value
provided at request time. The dataset does not document how `sla_breach` was
recorded or when a prediction was made, so it is suitable only as a prototype
sample, not as evidence of operational model performance.

## Prediction-Time Features

| Feature | Use | Leakage assessment |
| --- | --- | --- |
| `priority` | Ordinal categorical input | Allowed if set at ticket creation. |
| `created_hours` | Numeric elapsed ticket age | Allowed only when measured at prediction time. |
| `ticket_id` | Not used | Excluded to avoid identifier memorization. |
| `issue_type` | Not used | Available candidate for a future pipeline. |
| `assigned_team` | Not used | Excluded because it may be a post-triage outcome. |
| `sla_breach` | Target only | Never included in model features. |

## Data Quality Rules

Training data must have the three required fields, supported priorities,
`Yes`/`No` labels, and finite non-negative `created_hours`. Exact duplicate rows
are removed. Invalid categorical values and invalid ages fail training rather
than being silently remapped.

## Leakage Prevention and Evaluation

The pipeline owns priority encoding and is serialized with the estimator, so
training and inference use the same transformation and feature order. The
artifact also stores the expected schema and rejects legacy or corrupt payloads
before prediction.

The bundled dataset contains three unique tickets, two breach labels and one
non-breach label, with no timestamp. It cannot support a meaningful random,
stratified, grouped, or chronological hold-out evaluation. No accuracy, F1,
ROC-AUC, or PR-AUC is reported. A future dataset must include a documented
prediction timestamp and enough examples of each class; use chronological splits
when that timestamp reflects the production prediction sequence.

Joblib artifacts must be treated as trusted, locally generated files. Loading an
artifact from an untrusted source is unsafe because joblib deserialization can
execute code.
