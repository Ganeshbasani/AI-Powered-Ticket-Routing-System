# Product Workflows

The Flask application serves the static frontend at `/`. Users authenticate at
`POST /api/v1/auth/login`; protected API calls use `Authorization: Bearer <token>`.

| Role | Product access |
| --- | --- |
| Admin | Tickets, predictions, analytics, mock JIRA import, and user management. |
| Analyst | Tickets, prediction history, and analytics. |
| Support agent | Tickets and prediction requests. |

Ticket APIs support create, list, retrieve, and update. List queries accept
`limit`, `offset`, `search`, `priority`, `status`, and `team`; returned `total`
enables backend-backed pagination. Ticket predictions are append-only history.
The stored `actual_sla_breach` outcome is displayed separately and is never a
prediction input.

`GET /api/v1/analytics` reports only persisted ticket and prediction counts.
The frontend retains the prototype ML warning because the bundled three-row
dataset does not support performance claims. Mock JIRA import uses a Jira-shaped
payload and updates an existing ticket for the same issue key; no live JIRA
networking is implemented.
