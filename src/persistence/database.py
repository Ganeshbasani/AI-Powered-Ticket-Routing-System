"""SQLite database initialization with non-destructive versioned migrations."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS = [(1, """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'analyst', 'support_agent')), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY, jira_issue_key TEXT UNIQUE, summary TEXT NOT NULL, description TEXT,
    priority TEXT NOT NULL, created_hours REAL NOT NULL, assigned_team TEXT, status TEXT NOT NULL,
    source TEXT NOT NULL, actual_sla_breach TEXT CHECK(actual_sla_breach IN ('Yes', 'No')),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL REFERENCES tickets(id), predicted_risk TEXT NOT NULL,
    recommended_team TEXT NOT NULL, model_version TEXT NOT NULL, feature_schema TEXT NOT NULL,
    predicted_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY, actor_email TEXT, action TEXT NOT NULL, resource_type TEXT NOT NULL,
    resource_id TEXT, created_at TEXT NOT NULL
);
"""), (2, "ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0;"), (3, "ALTER TABLE tickets ADD COLUMN issue_type TEXT NOT NULL DEFAULT 'General';"), (4, """
ALTER TABLE predictions ADD COLUMN sla_probability REAL;
ALTER TABLE predictions ADD COLUMN routing_confidence REAL;
ALTER TABLE predictions ADD COLUMN explanation TEXT;
"""), (5, """
ALTER TABLE tickets ADD COLUMN project TEXT NOT NULL DEFAULT 'General';
ALTER TABLE tickets ADD COLUMN component TEXT NOT NULL DEFAULT 'General';
ALTER TABLE tickets ADD COLUMN customer_tier TEXT NOT NULL DEFAULT 'Standard';
ALTER TABLE tickets ADD COLUMN channel TEXT NOT NULL DEFAULT 'Portal';
"""), (6, """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    prediction_id INTEGER NOT NULL REFERENCES predictions(id),
    actor_email TEXT NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('accept', 'override')),
    corrected_team TEXT,
    corrected_sla_risk TEXT CHECK(corrected_sla_risk IN ('High', 'Low')),
    comment TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_ticket_id ON feedback(ticket_id);
CREATE INDEX IF NOT EXISTS idx_feedback_prediction_id ON feedback(prediction_id);
""")]


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.session() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)")
            applied = {row["version"] for row in connection.execute("SELECT version FROM schema_migrations")}
            for version, sql in MIGRATIONS:
                if version not in applied:
                    connection.executescript(sql)
                    connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
