"""WSGI entry point for the SLA prediction service."""

from __future__ import annotations

import os

from src.api.app import create_app
from src.config.settings import settings
from src.persistence.database import Database
from src.persistence.repository import TicketRepository


def bootstrap_user(
    repository: TicketRepository,
    email_env: str,
    password_env: str,
    role: str,
) -> None:
    """Create or reset a deployment user from environment variables."""
    email = os.environ.get(email_env)
    password = os.environ.get(password_env)

    if not email or not password:
        return

    user = repository.get_user_by_email(email)

    if user is None:
        repository.create_user(email, password, role)
        return

    repository.update_user(
        user["id"],
        role=role,
        disabled=False,
        password=password,
    )


def bootstrap_accounts() -> None:
    database = Database(settings.database_path)

    # Ensure all tables and migrations exist first.
    database.initialize()

    repository = TicketRepository(database)

    # Production administrator.
    bootstrap_user(
        repository,
        "BOOTSTRAP_ADMIN_EMAIL",
        "BOOTSTRAP_ADMIN_PASSWORD",
        "admin",
    )

    # Safe recruiter/demo account.
    bootstrap_user(
        repository,
        "DEMO_EMAIL",
        "DEMO_PASSWORD",
        os.environ.get("DEMO_ROLE", "analyst"),
    )


bootstrap_accounts()

app = create_app()

if __name__ == "__main__":
    app.run()
