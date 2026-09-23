"""ML-03: Evaluate classifier.

Measures the ML-02 model on held-out synthetic examples only
(``data/ml/test.jsonl`` — never the training set).

Metrics: accuracy plus per-label correct/total counts. The report records
the exact dataset path, model version and example IDs so judges can verify
no train/test leakage. The synthetic-data limitation is documented in
``docs/data-scenarios.md`` (ML-03 section).

Explicit failure states use :class:`EvaluationError` with a stable ``code``.

Consumer: team/judges; model metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEST_PATH = PROJECT_ROOT / "data" / "ml" / "test.jsonl"
TRAIN_PATH = PROJECT_ROOT / "data" / "ml" / "train.jsonl"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "ml"
EVALUATION_PATH = ARTIFACTS_DIR / "evaluation.json"

TASK_ID = "ML-03"


class EvaluationError(ValueError):
    """Controlled evaluation failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _require_joblib():
    try:
        import joblib
    except ImportError as exc:
        raise EvaluationError(
            "MISSING_DEPENDENCY",
            "joblib is required for evaluation. Install with: pip install joblib",
        ) from exc
    return joblib


def load_jsonl_ids(path: Path) -> set[str]:
    """Example IDs from a JSONL dataset (leakage check helper)."""
    ids: set[str] = set()
    with Path(path).open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                ids.add(json.loads(line)["example_id"])
    return ids


def evaluate(
    test_path: Path | str = TEST_PATH,
    artifacts_dir: Path | str = ARTIFACTS_DIR,
) -> dict[str, Any]:
    """Evaluate committed artifacts on the held-out set; return the report."""
    from app.ml.train import example_to_features, load_customers

    joblib = _require_joblib()
    artifacts = Path(artifacts_dir)
    test_src = Path(test_path)
    if not test_src.is_file():
        raise EvaluationError("TEST_NOT_FOUND", f"Held-out set not found: {test_src}")

    try:
        metadata = json.loads((artifacts / "model_metadata.json").read_text(encoding="utf-8"))
        vectorizer = joblib.load(artifacts / "vectorizer.joblib")
        classifier = joblib.load(artifacts / "classifier.joblib")
    except FileNotFoundError as exc:
        raise EvaluationError("ARTIFACTS_MISSING", f"ML-02 artifacts missing: {exc}") from exc
    except Exception as exc:
        raise EvaluationError("ARTIFACTS_UNREADABLE", f"Cannot load artifacts: {exc}") from exc

    customers = load_customers()
    test_examples: list[dict[str, Any]] = []
    with test_src.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                test_examples.append(json.loads(line))
    if not test_examples:
        raise EvaluationError("EMPTY_TEST_SET", f"Held-out set is empty: {test_src}")

    # Leakage guard: held-out IDs must not intersect the training IDs.
    train_ids = load_jsonl_ids(TRAIN_PATH)
    test_ids = {e["example_id"] for e in test_examples}
    overlap = train_ids & test_ids
    if overlap:
        raise EvaluationError("SPLIT_LEAKAGE", f"Test IDs overlap train IDs: {sorted(overlap)}")

    texts = [example_to_features(e, customers)[0] for e in test_examples]
    expected = [e["label"] for e in test_examples]
    predicted = [str(p) for p in classifier.predict(vectorizer.transform(texts))]

    per_label: dict[str, dict[str, int]] = {}
    correct = 0
    predictions: list[dict[str, str]] = []
    for example, exp, pred in zip(test_examples, expected, predicted):
        slot = per_label.setdefault(exp, {"correct": 0, "total": 0})
        slot["total"] += 1
        if exp == pred:
            slot["correct"] += 1
            correct += 1
        predictions.append(
            {"example_id": example["example_id"], "expected": exp, "predicted": pred}
        )

    return {
        "task_id": TASK_ID,
        "model_version": metadata.get("model_version"),
        "dataset": "data/ml/test.jsonl",
        "num_examples": len(test_examples),
        "example_ids": sorted(test_ids),
        "accuracy": correct / len(test_examples),
        "correct": correct,
        "per_label": per_label,
        "predictions": predictions,
        "limitation": (
            "Synthetic-only demo data (15 labeled cases); metrics describe "
            "prototype behavior on controlled fixtures, not production performance."
        ),
    }


def write_evaluation(
    report: dict[str, Any], path: Path | str = EVALUATION_PATH
) -> Path:
    """Persist the evaluation report."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return out


def evaluate_and_save(
    test_path: Path | str = TEST_PATH, path: Path | str = EVALUATION_PATH
) -> dict[str, Any]:
    """Evaluate on the canonical held-out set and persist the report."""
    report = evaluate(test_path)
    out = write_evaluation(report, path)
    print(
        f"Evaluated {report['num_examples']} held-out examples: "
        f"accuracy {report['accuracy']:.3f} -> {out.relative_to(PROJECT_ROOT).as_posix()}"
    )
    return report


__all__ = [
    "EvaluationError",
    "evaluate",
    "evaluate_and_save",
    "load_jsonl_ids",
    "write_evaluation",
    "EVALUATION_PATH",
    "TASK_ID",
    "TEST_PATH",
]
