# NLP Feature Foundation

Phase 8B introduces deterministic text preparation only. It does not train,
replace, or evaluate the current serialized SLA model.

## Input Semantics

| Field | Permitted at prediction time | Role |
| --- | --- | --- |
| `summary` | Yes | Short requester-provided text. |
| `description` | Yes | Requester-provided supporting text. |
| `issue_type`, `component`, `project` | Yes | Structured context available when a ticket is created. |
| `priority`, `created_hours`, `created_timestamp` | Yes | Existing structured prediction-time context. |
| `actual_sla_breach` | No | Observed SLA label only. |
| `final_status`, `final_team`, resolution fields | No | Post-resolution outcome fields only. |
| `ticket_id`, `jira_issue_key` | No | Lineage identifiers; excluded to prevent memorization. |

Raw `summary` and `description` remain separate canonical fields. A temporary
combined representation joins normalized summary and description with a blank
line; it never reads outcome fields.

## Normalization And Baseline

`src.data.nlp.normalize_text` applies Unicode NFKC normalization, HTML entity
decoding/tag removal, whitespace collapsing, conservative repeated-character
trimming, and a deterministic length cap. It preserves ordinary punctuation and
does not infer labels or delete source records.

`build_tfidf_pipeline` creates an unfitted scikit-learn TF-IDF baseline with
configurable n-grams, vocabulary size, and minimum document frequency. Its
configuration is deterministic, but it must be fitted only inside a future
chronological training workflow. It is not connected to the current production
model or API artifact.

## Leakage Review

The data validator flags text containing terms such as `resolved`, `closed`,
`actual SLA`, `SLA breach`, or `final team`. These warnings are review prompts,
not proof that text is invalid: requester text may legitimately use those
words. Confirm that each retained field was available at the intended scoring
time before training.

## Readiness Check

Run `python -m src.cli assess-dataset data/tickets.csv` for a JSON assessment
of row count, labels, text and timestamp coverage, missing values, duplicates,
and leakage warnings. The command reports separate SLA and routing readiness.
It uses a modest 100-row initial threshold and is deliberately conservative;
`READY` means only that basic evidence is present, not that model quality,
fairness, or production readiness has been established.
