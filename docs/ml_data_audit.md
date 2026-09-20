# ML Data and Leakage Audit

## Target and Prediction Point

Stage 1 uses two supervised learning targets:

- `final_team`: historical resolving team used as the routing target.
- `sla_breach`: observed SLA outcome where `Yes=1` and `No=0`.

Prediction-time inputs are limited to fields that can be known while the ticket is
being triaged: `summary`, `description`, `priority`, `issue_type`, `project`,
`component`, `customer_tier`, `channel`, and `created_hours`.

## Model Design

Both models use the same preprocessing contract:

- TF-IDF word/phrase features from `summary + description`
- One-hot encoding for categorical ticket metadata
- Standardized `created_hours`
- Logistic regression classifiers

Routing and SLA prediction are separate models so each target can be evaluated independently.

## Evaluation

The bundled development dataset contains 1,500 **synthetic** support tickets generated
from domain templates with modest label noise. A stratified 80/20 train/test split is used.

Current development benchmark produced by `ml_model/train_model.py`:

| Model | Accuracy | Precision | Recall | F1 |
|---|---:|---:|---:|---:|
| Routing | 0.9100 | 0.9294 | 0.9100 | 0.9170 |
| SLA | 0.8833 | 0.8964 | 0.8833 | 0.8861 |

These metrics are **not production performance claims**. The dataset is synthetic and exists
to make the end-to-end ML workflow reproducible. A future version should replace it with a
licensed, representative historical ticket dataset and preferably use a chronological split
when a trustworthy prediction timestamp is available.

## Leakage Prevention

The training feature schema excludes identifiers and outcome-only fields such as:
`ticket_id`, `final_team`, and `sla_breach`.

The resolving team is a target for the routing model; it is never supplied as a prediction feature.
The actual SLA outcome is likewise target-only.

## Artifact Safety

Joblib artifacts must be treated as trusted, locally generated files. Loading an artifact from
an untrusted source is unsafe because joblib deserialization can execute code.
