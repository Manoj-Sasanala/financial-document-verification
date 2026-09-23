"""ML-04: Runtime inference.

Predicts the configured case class (consistent | mismatch_detected |
insufficient_evidence) during verification using the ML-02 saved artifacts
and the ML-01 feature builder — never retraining.

Returns the frozen ``MLResult`` contract (classification + model_version)
for the explanation/orchestrator and reviewer UI consumers.

Explicit failure states use :class:`InferenceError` with a stable ``code``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.contracts import MLResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "ml"

TASK_ID = "ML-04"


class InferenceError(ValueError):
    """Controlled inference failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass
class LoadedModel:
    """Artifacts loaded once and reused for predictions."""

    vectorizer: Any
    classifier: Any
    model_version: str


def _require_joblib():
    try:
        import joblib
    except ImportError as exc:
        raise InferenceError(
            "MISSING_DEPENDENCY",
            "joblib is required for inference. Install with: pip install joblib",
        ) from exc
    return joblib


def load_artifacts(artifacts_dir: Path | str = ARTIFACTS_DIR) -> LoadedModel:
    """Load the saved vectorizer, classifier and model version (no retraining)."""
    joblib = _require_joblib()
    directory = Path(artifacts_dir)
    try:
        metadata = json.loads((directory / "model_metadata.json").read_text(encoding="utf-8"))
        vectorizer = joblib.load(directory / "vectorizer.joblib")
        classifier = joblib.load(directory / "classifier.joblib")
    except FileNotFoundError as exc:
        raise InferenceError("ARTIFACTS_MISSING", f"Model artifacts missing: {exc}") from exc
    except Exception as exc:
        raise InferenceError("ARTIFACTS_UNREADABLE", f"Cannot load artifacts: {exc}") from exc
    version = metadata.get("model_version")
    if not version:
        raise InferenceError("VERSION_MISSING", "model_metadata.json has no model_version.")
    return LoadedModel(vectorizer=vectorizer, classifier=classifier, model_version=str(version))


def predict_label(feature_text: str, model: LoadedModel | None = None) -> MLResult:
    """Predict the case class for one ML-01 feature text."""
    if not isinstance(feature_text, str) or not feature_text.strip():
        raise InferenceError("EMPTY_FEATURE_TEXT", "feature_text must be non-empty.")
    loaded = model if model is not None else load_artifacts()
    try:
        predicted = str(loaded.classifier.predict(loaded.vectorizer.transform([feature_text]))[0])
    except Exception as exc:
        raise InferenceError("PREDICTION_FAILED", f"Classifier failed: {exc}") from exc
    try:
        return MLResult(classification=predicted, model_version=loaded.model_version)  # type: ignore[arg-type]
    except Exception as exc:
        raise InferenceError(
            "INVALID_PREDICTION", f"Prediction {predicted!r} violates the label contract: {exc}"
        ) from exc


def predict_case(
    comparisons: list,
    indicators: list,
    findings: list | None = None,
    model: LoadedModel | None = None,
) -> MLResult:
    """Featurize a live case with ML-01 and predict its class."""
    from app.ml.features import build_feature_text

    try:
        text = build_feature_text(comparisons, indicators, findings)
    except Exception as exc:
        code = getattr(exc, "code", "FEATURE_BUILD_FAILED")
        raise InferenceError(code, f"Feature building failed: {exc}") from exc
    return predict_label(text, model)


__all__ = [
    "InferenceError",
    "LoadedModel",
    "load_artifacts",
    "predict_case",
    "predict_label",
    "ARTIFACTS_DIR",
    "TASK_ID",
]
