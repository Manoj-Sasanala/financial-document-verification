"""ML-02 entry point: train the TF-IDF + Logistic Regression classifier.

Usage:
    python scripts/train_ml.py
    python -m scripts.train_ml  (not supported; run as a script)

Writes artifacts/ml/vectorizer.joblib, artifacts/ml/classifier.joblib and
artifacts/ml/model_metadata.json.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ml.train import train_and_save  # noqa: E402


def main() -> None:
    train_and_save()


if __name__ == "__main__":
    main()
