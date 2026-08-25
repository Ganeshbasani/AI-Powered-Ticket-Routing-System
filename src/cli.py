"""Administrative commands that do not expose bootstrap operations over HTTP."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from src.config.settings import settings
from src.persistence.database import Database
from src.persistence.repository import TicketRepository
from src.data.pipeline import ingest, ingest_sqlite, profile_markdown, validate


def bootstrap_admin(email: str | None = None, password: str | None = None, database: Database | None = None) -> str:
    email = email or os.environ.get("BOOTSTRAP_ADMIN_EMAIL")
    password = password or os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
    if not email or not password:
        raise ValueError("BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD are required.")
    repository = TicketRepository(database or Database(settings.database_path)); repository.database.initialize()
    if repository.has_administrator():
        raise ValueError("An administrator already exists; bootstrap will not overwrite it.")
    repository.create_user(email, password, "admin")
    return "Administrator created."


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["bootstrap-admin", "validate-dataset", "profile-dataset"]); parser.add_argument("path", nargs="?"); parser.add_argument("--report", default="docs/dataset_profile.md"); args = parser.parse_args()
    if args.command == "bootstrap-admin": print(bootstrap_admin())
    elif args.command in {"validate-dataset", "profile-dataset"}:
        if not args.path: parser.error("path is required for dataset commands")
        frame = ingest_sqlite(args.path) if Path(args.path).suffix == ".db" else ingest(args.path)
        report = validate(frame)
        if args.command == "validate-dataset": print(report.as_dict())
        else:
            Path(args.report).write_text(profile_markdown(frame, report), encoding="utf-8"); print(f"Wrote {args.report}")


if __name__ == "__main__": main()
