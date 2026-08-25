# Security and Operations

Authenticate with `POST /api/v1/auth/login` using email and password, then send
`Authorization: Bearer <token>`. Tokens expire after one hour. Disabled users
cannot log in and are denied even when presenting a previously issued token.

Admins can use `GET /users`, `POST /users`, and `PATCH /users/{id}` to manage
users, roles, account status, and password resets. Analysts can view tickets and
prediction history; support agents can create tickets and request predictions.

Bootstrap the first administrator locally, never through HTTP:

```bash
set BOOTSTRAP_ADMIN_EMAIL=admin@example.com
set BOOTSTRAP_ADMIN_PASSWORD=use-a-strong-password
python -m src.cli bootstrap-admin
```

The command refuses to overwrite an existing administrator and never prints the
password. Login, prediction, and mock-JIRA import are rate limited per process;
distributed deployments require a shared limiter. The API limits requests to 1
MB and emits `nosniff` and `no-store` headers. Audit events intentionally omit
passwords, tokens, signing keys, and JIRA credentials.

The JIRA endpoint accepts only a local mock Jira-shaped payload. Live JIRA is
not implemented and configured JIRA credentials are never returned or logged.
