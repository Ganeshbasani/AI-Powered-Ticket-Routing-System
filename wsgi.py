"""WSGI entry point for the SLA prediction service."""

from src.api.app import create_app
from src.api.local_runner import run_local_app

app = create_app()

if __name__ == "__main__":
    run_local_app(app)
