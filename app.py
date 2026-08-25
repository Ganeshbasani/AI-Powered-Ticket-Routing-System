"""Entrypoint for running the SLA breach prediction service."""

from src.api.app import create_app
from src.config.settings import settings
from src.ml.model import ModelService


def main() -> None:
    model_service = ModelService()
    model_service.ensure_model()

    app = create_app()
    app.run(host=settings.flask_host, port=settings.flask_port, debug=settings.flask_debug)


if __name__ == "__main__":
    main()
