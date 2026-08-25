"""Repository boundary for the ticket platform."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from werkzeug.security import generate_password_hash

from src.persistence.database import Database


def _now() -> str:
    return datetime.now(UTC).isoformat()


class TicketRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_user(self, email: str, password: str, role: str) -> dict[str, Any]:
        with self.database.session() as connection:
            cursor = connection.execute(
                "INSERT INTO users(email, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (email.lower(), generate_password_hash(password), role, _now()),
            )
            return self.get_user_by_id(cursor.lastrowid, connection)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        with self.database.session() as connection:
            row = connection.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
            return dict(row) if row else None

    def list_users(self) -> list[dict[str, Any]]:
        with self.database.session() as connection:
            return [dict(row) for row in connection.execute("SELECT id, email, role, disabled, created_at FROM users ORDER BY id")]

    def update_user(self, user_id: int, *, role: str | None = None, disabled: bool | None = None, password: str | None = None) -> dict[str, Any] | None:
        assignments, values = [], []
        if role is not None: assignments.append("role = ?"); values.append(role)
        if disabled is not None: assignments.append("disabled = ?"); values.append(int(disabled))
        if password is not None: assignments.append("password_hash = ?"); values.append(generate_password_hash(password))
        if not assignments: return self.get_user_by_id(user_id)
        with self.database.session() as connection:
            connection.execute(f"UPDATE users SET {', '.join(assignments)} WHERE id = ?", (*values, user_id))
            return self.get_user_by_id(user_id, connection)

    def get_user_by_id(self, user_id: int, connection=None) -> dict[str, Any] | None:
        if connection is None:
            with self.database.session() as owned_connection:
                return self.get_user_by_id(user_id, owned_connection)
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def upsert_ticket(self, ticket: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        with self.database.session() as connection:
            existing = None
            if ticket.get("jira_issue_key"):
                existing = connection.execute("SELECT id FROM tickets WHERE jira_issue_key = ?", (ticket["jira_issue_key"],)).fetchone()
            values = (ticket["summary"], ticket.get("description"), ticket["priority"], ticket["created_hours"], ticket.get("assigned_team"), ticket.get("status", "open"), ticket.get("source", "api"), ticket.get("actual_sla_breach"), now)
            if existing:
                connection.execute("UPDATE tickets SET summary=?, description=?, priority=?, created_hours=?, assigned_team=?, status=?, source=?, actual_sla_breach=?, updated_at=? WHERE id=?", (*values, existing["id"]))
                ticket_id = existing["id"]
            else:
                cursor = connection.execute("INSERT INTO tickets(jira_issue_key, summary, description, priority, created_hours, assigned_team, status, source, actual_sla_breach, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (ticket.get("jira_issue_key"), *values, now))
                ticket_id = cursor.lastrowid
            return self.get_ticket(ticket_id, connection)

    def get_ticket(self, ticket_id: int, connection=None) -> dict[str, Any] | None:
        if connection is None:
            with self.database.session() as owned_connection:
                return self.get_ticket(ticket_id, owned_connection)
        row = connection.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return dict(row) if row else None

    def update_ticket(self, ticket_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"summary", "description", "priority", "created_hours", "assigned_team", "status"}
        updates = {name: value for name, value in fields.items() if name in allowed}
        if not updates:
            return self.get_ticket(ticket_id)
        assignments = [f"{name} = ?" for name in updates]
        values = [*updates.values(), _now(), ticket_id]
        with self.database.session() as connection:
            connection.execute(f"UPDATE tickets SET {', '.join(assignments)}, updated_at = ? WHERE id = ?", values)
            return self.get_ticket(ticket_id, connection)

    def list_tickets(self, limit: int, offset: int, priority: str | None = None, status: str | None = None, team: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
        query, params = "SELECT * FROM tickets", []
        clauses = []
        if priority: clauses.append("priority = ?"); params.append(priority)
        if status: clauses.append("status = ?"); params.append(status)
        if team: clauses.append("assigned_team = ?"); params.append(team)
        if search: clauses.append("(summary LIKE ? OR jira_issue_key LIKE ?)"); params.extend([f"%{search}%", f"%{search}%"])
        if clauses: query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"; params.extend([limit, offset])
        with self.database.session() as connection:
            return [dict(row) for row in connection.execute(query, params)]

    def ticket_count(self, priority: str | None = None, status: str | None = None, team: str | None = None, search: str | None = None) -> int:
        clauses, params = [], []
        if priority: clauses.append("priority = ?"); params.append(priority)
        if status: clauses.append("status = ?"); params.append(status)
        if team: clauses.append("assigned_team = ?"); params.append(team)
        if search: clauses.append("(summary LIKE ? OR jira_issue_key LIKE ?)"); params.extend([f"%{search}%", f"%{search}%"])
        query = "SELECT COUNT(*) FROM tickets" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        with self.database.session() as connection: return connection.execute(query, params).fetchone()[0]

    def analytics(self) -> dict[str, Any]:
        with self.database.session() as connection:
            group = lambda field: {row[0] or "Unassigned": row[1] for row in connection.execute(f"SELECT {field}, COUNT(*) FROM tickets GROUP BY {field}")}
            return {"total_tickets": connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0], "open_tickets": connection.execute("SELECT COUNT(*) FROM tickets WHERE lower(status) = 'open'").fetchone()[0], "by_priority": group("priority"), "by_status": group("status"), "by_team": group("assigned_team"), "prediction_count": connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0], "predicted_breaches": connection.execute("SELECT COUNT(*) FROM predictions WHERE predicted_risk = 'High'").fetchone()[0]}

    def add_prediction(self, ticket_id: int, prediction: dict[str, str]) -> dict[str, Any]:
        with self.database.session() as connection:
            cursor = connection.execute("INSERT INTO predictions(ticket_id, predicted_risk, recommended_team, model_version, feature_schema, predicted_at) VALUES (?, ?, ?, ?, ?, ?)", (ticket_id, prediction["sla_breach_risk"], prediction["assigned_team"], prediction["model_version"], json.dumps(["priority", "created_hours"]), _now()))
            row = connection.execute("SELECT * FROM predictions WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return dict(row)

    def predictions_for_ticket(self, ticket_id: int) -> list[dict[str, Any]]:
        with self.database.session() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM predictions WHERE ticket_id = ? ORDER BY id DESC", (ticket_id,))]

    def audit(self, actor_email: str | None, action: str, resource_type: str, resource_id: str | None) -> None:
        with self.database.session() as connection:
            connection.execute("INSERT INTO audit_events(actor_email, action, resource_type, resource_id, created_at) VALUES (?, ?, ?, ?, ?)", (actor_email, action, resource_type, resource_id, _now()))

    def audit_events(self) -> list[dict[str, Any]]:
        with self.database.session() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM audit_events ORDER BY id")]

    def has_administrator(self) -> bool:
        with self.database.session() as connection:
            return connection.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone() is not None
