"""Administrative commands that do not expose bootstrap operations over HTTP."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.config.settings import settings
from src.persistence.database import Database
from src.persistence.repository import TicketRepository
from src.data.pipeline import assess_readiness, ingest, ingest_sqlite, profile_markdown, validate
from src.data.synthetic import SIZE_PRESETS, write_synthetic_dataset
from src.ml.candidates import train_candidate_models


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
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bootstrap-admin", "validate-dataset", "profile-dataset", "assess-dataset", "generate-synthetic", "train-candidates"])
    parser.add_argument("path", nargs="?")
    parser.add_argument("--report", default="docs/dataset_profile.md")
    parser.add_argument("--size", choices=sorted(SIZE_PRESETS), default="medium")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--manifest")
    parser.add_argument("--artifacts", default="ml_model/candidates")
    args = parser.parse_args()
    if args.command == "bootstrap-admin": print(bootstrap_admin())
    elif args.command == "generate-synthetic":
        output = Path(args.path or f"data/synthetic/{args.size}.csv")
        manifest = Path(args.manifest or output.with_suffix(".manifest.json"))
        result = write_synthetic_dataset(output, manifest, record_count=SIZE_PRESETS[args.size], seed=args.seed)
        print(json.dumps({"data_path": str(output), "manifest_path": str(manifest), **result.as_dict()}, indent=2, sort_keys=True))
    elif args.command == "train-candidates":
        if not args.path: parser.error("path is required for candidate training")
        manifest = Path(args.manifest or Path(args.path).with_suffix(".manifest.json"))
        print(json.dumps(train_candidate_models(args.path, manifest, args.artifacts), indent=2, sort_keys=True))
    elif args.command in {"validate-dataset", "profile-dataset", "assess-dataset"}:
        if not args.path: parser.error("path is required for dataset commands")
        frame = ingest_sqlite(args.path) if Path(args.path).suffix == ".db" else ingest(args.path)
        report = validate(frame)
        if args.command == "validate-dataset": print(report.as_dict())
        elif args.command == "assess-dataset": print(json.dumps(assess_readiness(frame).as_dict(), indent=2, sort_keys=True))
        else:
            Path(args.report).write_text(profile_markdown(frame, report), encoding="utf-8"); print(f"Wrote {args.report}")


if __name__ == "__main__": main()
