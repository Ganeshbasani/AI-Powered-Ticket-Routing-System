"""Entrypoint for running the SLA breach prediction service."""

from src.api.app import create_app
from src.api.local_runner import run_local_app


def main() -> None:
    app = create_app()
    run_local_app(app)


if __name__ == "__main__":
    main()
