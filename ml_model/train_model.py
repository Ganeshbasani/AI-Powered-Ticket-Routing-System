"""Standalone training script for the SLA prediction model."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from src.ml.model import ModelService


def main() -> None:
    service = ModelService()
    service.ensure_model()


if __name__ == "__main__":
    main()
