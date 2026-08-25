# Platform API

The local platform uses SQLite at `DATABASE_PATH` and applies non-destructive,
versioned schema migrations at application startup. `tickets.actual_sla_breach`
is an outcome field and is never passed to the prediction model. Each ticket
prediction is appended to `predictions`; historical rows are not overwritten.

Authentication uses expiring, signed bearer tokens through Flask's
`itsdangerous` dependency. Set `AUTH_SECRET_KEY` in production. Roles are
`admin`, `analyst`, and `support_agent`; ticket mutation and prediction require
admin or support-agent access, while mock JIRA import is admin-only.

Implemented endpoints include `POST /api/v1/auth/login`, ticket create/list/get,
ticket prediction/history, and `POST /api/v1/integrations/jira/import`. The
JIRA endpoint accepts a local Jira-shaped `issue` payload and uses `key` as the
idempotency key. It does not contact a live JIRA instance. Live JIRA credentials
in `.env.example` are placeholders for a future provider implementation.
