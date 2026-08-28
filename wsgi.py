"""WSGI entry point for the SLA prediction service."""

from __future__ import annotations

import os

from src.api.app import create_app
from src.config.settings import settings
from src.persistence.database import Database
from src.persistence.repository import TicketRepository


def bootstrap_admin() -> None:
    """Create or reset the deployment administrator safely."""
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL")
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")

    if not email or not password:
        return

    database = Database(settings.database_path)

    # IMPORTANT: create database/tables before accessing users.
    database.initialize()

    repository = TicketRepository(database)

    user = repository.get_user_by_email(email)

    if user is None:
        repository.create_user(email, password, "admin")
        return

    repository.update_user(
        user["id"],
        role="admin",
        disabled=False,
        password=password,
    )


bootstrap_admin()

app = create_app()

if __name__ == "__main__":
    app.run()
