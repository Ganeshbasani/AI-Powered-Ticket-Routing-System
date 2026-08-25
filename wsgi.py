"""WSGI entry point for the SLA prediction service."""

from src.api.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
