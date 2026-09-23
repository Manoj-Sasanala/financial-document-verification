"""ML-02: Train TF-IDF + Logistic Regression.

Builds the required classifier from the DATA-06 labeled training set using
the ML-01 feature function.

Pipeline per labeled example (deterministic, end to end):
  1. Synthesize document text from the example ``observed`` record using
     DATA-03 template labels.
  2. Parse (DOC-04), normalize (VER-01), validate (VER-02).
  3. Resolve the reference: known customer via the customers dataset,
     unknown customer (CUST-9999) as ``reference_found=False``.
  4. Compare (VER-04), assess risk (VER-05).
  5. Build ML-01 feature text; label is the example label.

Model: ``TfidfVectorizer`` + ``LogisticRegression`` (fixed seeds/hparams).
Artifacts (canonical): ``artifacts/ml/vectorizer.joblib``,
``artifacts/ml/classifier.joblib``, ``artifacts/ml/model_metadata.json``.

Explicit failure states use :class:`TrainingError` with a stable ``code``.

Consumer: ML inference (ML-04); API orchestrator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

TRAIN_PATH = PROJECT_ROOT / "data" / "ml" / "train.jsonl"
CUSTOMERS_PATH = PROJECT_ROOT / "data" / "synthetic" / "customers.json"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "ml"

MODEL_VERSION = "1.0.0"
TASK_ID = "ML-02"
RANDOM_STATE = 42


class TrainingError(ValueError):
    """Controlled training failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _require_sklearn():
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise TrainingError(
            "MISSING_DEPENDENCY",
            "scikit-learn is required for training. Install with: pip install scikit-learn",
        ) from exc
    return TfidfVectorizer, LogisticRegression


def load_labeled_examples(path: Path | str = TRAIN_PATH) -> list[dict[str, Any]]:
    """Load DATA-06 JSONL examples (one per line)."""
    src = Path(path)
    if not src.is_file():
        raise TrainingError("TRAIN_NOT_FOUND", f"Labeled training set not found: {src}")
    examples: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                examples.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise TrainingError(
                    "INVALID_TRAIN_JSONL", f"Invalid JSON on line {lineno}: {exc}"
                ) from exc
    if not examples:
        raise TrainingError("EMPTY_TRAIN_SET", f"Training set is empty: {src}")
    return examples


def load_customers(path: Path | str = CUSTOMERS_PATH) -> dict[str, dict[str, str]]:
    """Load the synthetic customer dataset keyed by customer_id."""
    src = Path(path)
    if not src.is_file():
        raise TrainingError("CUSTOMERS_NOT_FOUND", f"customers.json not found: {src}")
    try:
        customers = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TrainingError("INVALID_CUSTOMERS", f"Invalid customers.json: {exc}") from exc
    return {c["customer_id"]: c for c in customers}


def synthesize_document_text(observed: dict[str, Any]) -> str:
    """Render observed record as template-label document text for parsing."""
    lines = [
        "Customer ID",
        str(observed.get("customer_id", "")),
        "Customer Name",
        str(observed.get("customer_name", "")),
        "Address",
        str(observed.get("address", "")),
        "Postal Code",
        str(observed.get("postal_code", "")),
    ]
    if observed.get("document_type"):
        lines += ["Document Type", str(observed["document_type"])]
    if observed.get("document_date"):
        lines += ["Document Date", str(observed["document_date"])]
    return "\n".join(lines)


def example_to_features(
    example: dict[str, Any], customers: dict[str, dict[str, str]]
) -> tuple[str, str]:
    """Convert one labeled example to (feature_text, label) end to end."""
    from app.document.field_parser import parse_fields
    from app.ml.features import build_feature_text
    from app.verification.compare import compare_fields
    from app.verification.normalize import normalize_fields
    from app.verification.risk_rules import assess_risk
    from app.verification.validate import validate_fields

    observed = example.get("observed") or {}
    label = example.get("label")
    if not label:
        raise TrainingError("MISSING_LABEL", f"Example {example.get('example_id')} has no label.")

    text = synthesize_document_text(observed)
    normalized = normalize_fields(parse_fields(text).fields)
    findings = validate_fields(normalized)

    customer_id = str(observed.get("customer_id", ""))
    reference = customers.get(customer_id)
    reference_found = reference is not None
    comparisons = compare_fields(normalized, reference)
    indicators = assess_risk(
        findings,
        comparisons,
        reference_found=reference_found,
        document_type=observed.get("document_type"),
    )
    return build_feature_text(comparisons, indicators, findings), str(label)


def train(
    examples: list[dict[str, Any]] | None = None,
    customers: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Train vectorizer + classifier; return bundle with texts and labels."""
    TfidfVectorizer, LogisticRegression = _require_sklearn()

    examples = examples if examples is not None else load_labeled_examples()
    customers = customers if customers is not None else load_customers()

    texts: list[str] = []
    labels: list[str] = []
    for example in examples:
        text, label = example_to_features(example, customers)
        texts.append(text)
        labels.append(label)

    vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2))
    matrix = vectorizer.fit_transform(texts)
    classifier = LogisticRegression(max_iter=1000, random_state=RANDOM_STATE)
    classifier.fit(matrix, labels)

    try:
        import sklearn

        sklearn_version: str | None = sklearn.__version__
    except Exception:
        sklearn_version = None

    return {
        "vectorizer": vectorizer,
        "classifier": classifier,
        "texts": texts,
        "labels": labels,
        "model_version": MODEL_VERSION,
        "sklearn_version": sklearn_version,
    }


def save_artifacts(bundle: dict[str, Any], out_dir: Path | str = ARTIFACTS_DIR) -> Path:
    """Persist vectorizer, classifier and versioned model metadata."""
    try:
        import joblib
    except ImportError as exc:
        raise TrainingError(
            "MISSING_DEPENDENCY",
            "joblib is required to save artifacts. Install with: pip install joblib",
        ) from exc

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle["vectorizer"], out / "vectorizer.joblib")
    joblib.dump(bundle["classifier"], out / "classifier.joblib")
    metadata = {
        "model_version": bundle["model_version"],
        "task_id": TASK_ID,
        "feature_schema": "1.0.0",
        "model": "TfidfVectorizer(1,2)+LogisticRegression",
        "random_state": RANDOM_STATE,
        "sklearn_version": bundle.get("sklearn_version"),
        "num_train_examples": len(bundle["labels"]),
        "labels": sorted(set(bundle["labels"])),
    }
    (out / "model_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return out


def train_and_save(
    train_path: Path | str = TRAIN_PATH, out_dir: Path | str = ARTIFACTS_DIR
) -> dict[str, Any]:
    """Train on the canonical set and save artifacts; return metadata."""
    bundle = train(load_labeled_examples(train_path))
    out = save_artifacts(bundle, out_dir)
    print(
        f"Trained on {len(bundle['labels'])} examples "
        f"-> {out.relative_to(PROJECT_ROOT).as_posix()}"
    )
    return bundle


__all__ = [
    "TrainingError",
    "example_to_features",
    "load_customers",
    "load_labeled_examples",
    "save_artifacts",
    "synthesize_document_text",
    "train",
    "train_and_save",
    "ARTIFACTS_DIR",
    "MODEL_VERSION",
    "TASK_ID",
    "TRAIN_PATH",
]
