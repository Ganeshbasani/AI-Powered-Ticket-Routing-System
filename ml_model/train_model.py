"""Standalone training script for the ticket triage models."""

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
    print("Model version:", "triage-v1.0")
    print("Evaluation:")
    for name, metrics in service.evaluation.items():
        print(f"  {name}: {metrics}")


if __name__ == "__main__":
    main()
