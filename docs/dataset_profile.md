# Dataset Profile

- Rows: 3
- Schema version: 1.0
- Validation status: valid
- Missing values: {'jira_issue_key': 3, 'project': 3, 'component': 3, 'summary': 3, 'description': 3, 'created_timestamp': 3, 'resolution_timestamp': 3, 'resolution_time': 3, 'final_status': 3}
- Exact duplicates: 0
- Priority distribution: {'High': 2, 'Medium': 1}
- Issue-type distribution: {'Bug': 1, 'Task': 1, 'Incident': 1}
- SLA outcome distribution: {'Yes': 2, 'No': 1}
- Text availability: {'summary': 0, 'description': 0}
- Timestamp coverage: 0

## Leakage Warnings
- ticket_id is an identifier and may enable memorization.
- jira_issue_key is an identifier and may enable memorization.
- actual_sla_breach is outcome-only and must not be a prediction feature.
- resolution_timestamp is outcome-only and must not be a prediction feature.
- resolution_time is outcome-only and must not be a prediction feature.
- final_status is outcome-only and must not be a prediction feature.
- final_team is outcome-only and must not be a prediction feature.

## Limitation
The bundled prototype contains 3 records and cannot support meaningful ML evaluation.