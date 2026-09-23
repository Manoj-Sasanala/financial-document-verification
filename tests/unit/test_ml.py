"""DATA-06 verification: ML labeled cases.

Canonical storage (per repo file-structure map):
  data/ml/train.jsonl
  data/ml/test.jsonl
(one labeled example per line.)

DoD: Labeled files are loadable and class labels match the Step 6 contract.
Test: Classes are represented in both datasets without reusing the same
exact examples across train and test.
"""

import json
from collections import Counter
from pathlib import Path

from app.core.contracts import MLResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAIN_PATH = PROJECT_ROOT / "data" / "ml" / "train.jsonl"
TEST_PATH = PROJECT_ROOT / "data" / "ml" / "test.jsonl"
SCENARIOS_PATH = PROJECT_ROOT / "data" / "synthetic" / "scenarios.json"

ALLOWED_LABELS = {"consistent", "mismatch_detected", "insufficient_evidence"}

REQUIRED_EXAMPLE_FIELDS = {
    "example_id",
    "split",
    "label",
    "scenario_type",
    "source_scenario_id",
    "customer_id",
    "features",
    "reference",
    "observed",
    "provenance",
}


def load_dataset(path: Path) -> list[dict]:
    """Load a JSONL dataset: one example per line, blank lines skipped."""
    examples: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            obj = json.loads(line)
            assert isinstance(obj, dict), f"{path} line {lineno} must be an object"
            examples.append(obj)
    return examples


def test_train_and_test_files_exist_and_load() -> None:
    assert TRAIN_PATH.is_file(), f"Missing {TRAIN_PATH}"
    assert TEST_PATH.is_file(), f"Missing {TEST_PATH}"
    train = load_dataset(TRAIN_PATH)
    test = load_dataset(TEST_PATH)
    assert len(train) == 9, f"expected 9 train examples, got {len(train)}"
    assert len(test) == 6, f"expected 6 test examples, got {len(test)}"
    for example in train:
        assert example["split"] == "train", example["example_id"]
    for example in test:
        assert example["split"] == "test", example["example_id"]


def test_label_counts_match_expected_split_plan() -> None:
    train_counts = Counter(e["label"] for e in load_dataset(TRAIN_PATH))
    test_counts = Counter(e["label"] for e in load_dataset(TEST_PATH))
    assert train_counts == {
        "consistent": 3,
        "mismatch_detected": 3,
        "insufficient_evidence": 3,
    }, dict(train_counts)
    assert test_counts == {
        "consistent": 2,
        "mismatch_detected": 2,
        "insufficient_evidence": 2,
    }, dict(test_counts)


def test_labels_match_step6_mlresult_contract() -> None:
    for path in (TRAIN_PATH, TEST_PATH):
        for example in load_dataset(path):
            assert example["label"] in ALLOWED_LABELS
            # Frozen Step 9.6 / Step 6 contract: MLResult must accept the label.
            result = MLResult(classification=example["label"], model_version="test")
            assert result.classification == example["label"]


def test_all_classes_represented_in_both_splits() -> None:
    train_labels = {e["label"] for e in load_dataset(TRAIN_PATH)}
    test_labels = {e["label"] for e in load_dataset(TEST_PATH)}
    assert train_labels == ALLOWED_LABELS, f"train missing {ALLOWED_LABELS - train_labels}"
    assert test_labels == ALLOWED_LABELS, f"test missing {ALLOWED_LABELS - test_labels}"


def test_no_exact_examples_reused_across_splits() -> None:
    train = load_dataset(TRAIN_PATH)
    test = load_dataset(TEST_PATH)

    train_ids = [e["example_id"] for e in train]
    test_ids = [e["example_id"] for e in test]
    assert len(set(train_ids)) == len(train_ids), "duplicate example_id in train"
    assert len(set(test_ids)) == len(test_ids), "duplicate example_id in test"
    assert not (set(train_ids) & set(test_ids)), "example_id reused across splits"

    def dedup_key(e: dict) -> tuple:
        return (
            str(e["scenario_type"]),
            str(e["observed"].get("customer_id")),
            str(e["label"]),
        )

    overlap = {dedup_key(e) for e in train} & {dedup_key(e) for e in test}
    assert not overlap, f"exact (scenario, customer, label) reused: {overlap}"

    train_payloads = {json.dumps(e, sort_keys=True) for e in train}
    test_payloads = {json.dumps(e, sort_keys=True) for e in test}
    assert not (train_payloads & test_payloads), "identical payload in both splits"


def test_examples_have_required_fields_and_provenance() -> None:
    for path in (TRAIN_PATH, TEST_PATH):
        for example in load_dataset(path):
            assert REQUIRED_EXAMPLE_FIELDS <= set(example.keys()), example["example_id"]
            prov = example["provenance"]
            assert prov["task_id"] == "DATA-06"
            assert prov["synthetic_only"] is True
            assert prov["source_scenarios"] == "data/synthetic/scenarios.json"
            assert prov["source_scenario_id"]
            assert isinstance(example["features"], dict)
            assert isinstance(example["reference"], dict)
            assert isinstance(example["observed"], dict)


def test_source_scenarios_come_from_data04_data05() -> None:
    with SCENARIOS_PATH.open("r", encoding="utf-8") as fh:
        scenarios = json.load(fh)
    valid_ids = {s["scenario_id"] for s in scenarios["scenarios"]}
    for path in (TRAIN_PATH, TEST_PATH):
        for example in load_dataset(path):
            assert example["source_scenario_id"] in valid_ids, (
                f"{example['example_id']} references unknown {example['source_scenario_id']}"
            )


def test_datasets_are_synthetic_only() -> None:
    # Guard against real PII leaking into the ML dataset.
    forbidden = ["@gmail.com", "@yahoo.com", "SSN", "AKIA"]
    for path in (TRAIN_PATH, TEST_PATH):
        raw = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in raw


# ---------------------------------------------------------------------------
# ML-01: Feature text (DoD: schema documented and implemented; same case
# produces identical feature text)
# ---------------------------------------------------------------------------

import pytest as _pytest  # noqa: E402

from app.ml.features import (  # noqa: E402
    FEATURE_SCHEMA_VERSION as _SCHEMA,
)
from app.ml.features import FeatureError as _FeatureError
from app.ml.features import build_feature_text as _feature_text


def _ml_case(kind: str = "clean"):
    from app.document.field_parser import parse_fields as _parse
    from app.verification.compare import compare_fields as _compare
    from app.verification.normalize import normalize_fields as _nf
    from app.verification.risk_rules import assess_risk as _assess
    from app.verification.validate import validate_fields as _validate

    texts = {
        "clean": "Customer Name\nAarav Mehta\nAddress\n42 Example Avenue, Vijayawada\nPostal Code\n520001",
        "name": "Customer Name\nAarav Sharma\nAddress\n42 Example Avenue, Vijayawada\nPostal Code\n520001",
    }
    ref = {
        "customer_id": "CUST-0001",
        "customer_name": "Aarav Mehta",
        "address": "42 Example Avenue, Vijayawada",
        "postal_code": "520001",
    }
    normalized = _nf(_parse(texts[kind]).fields)
    findings = _validate(normalized)
    comparisons = _compare(normalized, ref)
    indicators = _assess(findings, comparisons)
    return comparisons, indicators, findings


def test_same_case_produces_identical_feature_text() -> None:
    case = _ml_case("clean")

    assert _feature_text(*case) == _feature_text(*case)


def test_feature_text_follows_documented_schema() -> None:
    comparisons, indicators, findings = _ml_case("clean")
    text = _feature_text(comparisons, indicators, findings)
    lines = text.strip().splitlines()

    assert lines[0] == f"schema {_SCHEMA}"
    assert lines[1].startswith("field customer_name match")
    assert "aarav mehta => aarav mehta" in lines[1]


def test_mismatch_case_changes_feature_text() -> None:
    assert _feature_text(*_ml_case("clean")) != _feature_text(*_ml_case("name"))
    assert "indicator name_mismatch RISK-001 warning" in _feature_text(*_ml_case("name"))


def test_empty_comparisons_is_explicit() -> None:
    with _pytest.raises(_FeatureError) as exc_info:
        _feature_text([], [])
    assert exc_info.value.code == "EMPTY_COMPARISONS"


# ---------------------------------------------------------------------------
# ML-02: Train TF-IDF + Logistic Regression (DoD: saved artifacts exist with
# a recorded model version; training completes and artifacts load)
# ---------------------------------------------------------------------------

import joblib as _joblib  # noqa: E402

from app.ml.train import (  # noqa: E402
    ARTIFACTS_DIR as _ARTIFACTS,
)
from app.ml.train import example_to_features as _ex_features
from app.ml.train import load_customers as _load_customers
from app.ml.train import load_labeled_examples as _load_examples
from app.ml.train import save_artifacts as _save_artifacts
from app.ml.train import train as _train


def test_training_completes_with_versioned_metadata(tmp_path) -> None:
    bundle = _train()

    assert bundle["model_version"] == "1.0.0"
    assert len(bundle["texts"]) == 9
    assert set(bundle["labels"]) == {
        "consistent",
        "mismatch_detected",
        "insufficient_evidence",
    }

    out = _save_artifacts(bundle, tmp_path / "artifacts")

    assert (out / "vectorizer.joblib").is_file()
    assert (out / "classifier.joblib").is_file()
    metadata = json.loads((out / "model_metadata.json").read_text(encoding="utf-8"))
    assert metadata["model_version"] == "1.0.0"
    assert metadata["num_train_examples"] == 9


def test_saved_artifacts_load_and_predict(tmp_path) -> None:
    bundle = _train()
    out = _save_artifacts(bundle, tmp_path / "artifacts")

    vectorizer = _joblib.load(out / "vectorizer.joblib")
    classifier = _joblib.load(out / "classifier.joblib")

    predicted = classifier.predict(vectorizer.transform(bundle["texts"]))

    assert set(predicted) <= set(bundle["labels"])
    assert len(predicted) == len(bundle["texts"])


def test_labeled_examples_bridge_to_feature_text() -> None:
    examples = _load_examples()
    customers = _load_customers()

    texts_labels = [_ex_features(e, customers) for e in examples]

    assert len(texts_labels) == 9
    for text, label in texts_labels:
        assert text.startswith("schema 1.0.0")
        assert label in {"consistent", "mismatch_detected", "insufficient_evidence"}


def test_committed_artifacts_exist_with_version(tmp_path) -> None:
    _ = tmp_path
    assert (_ARTIFACTS / "vectorizer.joblib").is_file()
    assert (_ARTIFACTS / "classifier.joblib").is_file()
    metadata = json.loads((_ARTIFACTS / "model_metadata.json").read_text(encoding="utf-8"))
    assert metadata["model_version"] == "1.0.0"


# ---------------------------------------------------------------------------
# ML-03: Evaluate classifier (DoD: metric generated + synthetic limitation
# documented; held-out only with dataset/version recorded)
# ---------------------------------------------------------------------------

from app.ml.evaluate import evaluate as _evaluate  # noqa: E402
from app.ml.evaluate import load_jsonl_ids as _ids  # noqa: E402


def test_evaluation_runs_on_committed_artifacts() -> None:
    report = _evaluate()

    assert report["model_version"] == "1.0.0"
    assert report["dataset"] == "data/ml/test.jsonl"
    assert report["num_examples"] == 6
    assert 0.0 <= report["accuracy"] <= 1.0
    assert set(report["per_label"]) == {
        "consistent",
        "mismatch_detected",
        "insufficient_evidence",
    }
    assert len(report["predictions"]) == 6


def test_evaluation_uses_only_held_out_examples() -> None:
    report = _evaluate()

    assert set(report["example_ids"]) == _ids(PROJECT_ROOT / "data" / "ml" / "test.jsonl")
    assert not (set(report["example_ids"]) & _ids(PROJECT_ROOT / "data" / "ml" / "train.jsonl"))


def test_evaluation_records_version_and_limitation(tmp_path) -> None:
    from app.ml.evaluate import write_evaluation as _write

    report = _evaluate()
    out = _write(report, tmp_path / "evaluation.json")
    stored = json.loads(out.read_text(encoding="utf-8"))

    assert stored["model_version"] == "1.0.0"
    assert "Synthetic-only" in stored["limitation"] or "synthetic" in stored["limitation"]


def test_synthetic_limitation_is_documented() -> None:
    doc = (PROJECT_ROOT / "docs" / "data-scenarios.md").read_text(encoding="utf-8")

    assert "ML-03" in doc
    assert "data/ml/test.jsonl" in doc
    assert "must not be interpreted as production" in doc


# ---------------------------------------------------------------------------
# ML-04: Runtime inference (DoD: loads saved artifacts without retraining;
# prepared samples return valid configured labels)
# ---------------------------------------------------------------------------

from app.core.contracts import MLResult as _MLResult  # noqa: E402
from app.ml.inference import (  # noqa: E402
    InferenceError as _InferenceError,
)
from app.ml.inference import load_artifacts as _load
from app.ml.inference import predict_case as _predict_case
from app.ml.inference import predict_label as _predict


def _valid_labels() -> set:
    return {"consistent", "mismatch_detected", "insufficient_evidence"}


def test_inference_loads_artifacts_without_retraining() -> None:
    model = _load()

    assert model.model_version == "1.0.0"
    assert hasattr(model.vectorizer, "transform")
    assert hasattr(model.classifier, "predict")


def test_prepared_cases_return_valid_labels() -> None:
    clean_text = _feature_text(*_ml_case("clean"))
    mismatch_text = _feature_text(*_ml_case("name"))

    clean = _predict(clean_text)
    mismatch = _predict(mismatch_text)

    assert isinstance(clean, _MLResult)
    assert clean.classification in _valid_labels()
    assert mismatch.classification in _valid_labels()
    assert clean.model_version == "1.0.0"


def test_predict_case_end_to_end() -> None:
    from app.document.field_parser import parse_fields as _parse
    from app.verification.compare import compare_fields as _cmp
    from app.verification.normalize import normalize_fields as _nf
    from app.verification.risk_rules import assess_risk as _ar
    from app.verification.validate import validate_fields as _vf

    ref = {
        "customer_id": "CUST-0001",
        "customer_name": "Aarav Mehta",
        "address": "42 Example Avenue, Vijayawada",
        "postal_code": "520001",
    }
    normalized = _nf(_parse("Customer Name\nAarav Mehta\nAddress\n42 Example Avenue, Vijayawada\nPostal Code\n520001").fields)
    findings = _vf(normalized)
    comparisons = _cmp(normalized, ref)
    indicators = _ar(findings, comparisons)

    result = _predict_case(comparisons, indicators, findings)

    assert result.classification in _valid_labels()


def test_inference_is_deterministic() -> None:
    text = _feature_text(*_ml_case("clean"))

    assert _predict(text).classification == _predict(text).classification


def test_missing_artifacts_is_explicit(tmp_path) -> None:
    with _pytest.raises(_InferenceError) as exc_info:
        _load(tmp_path / "nope")
    assert exc_info.value.code == "ARTIFACTS_MISSING"


def test_empty_feature_text_is_explicit() -> None:
    with _pytest.raises(_InferenceError) as exc_info:
        _predict("   ")
    assert exc_info.value.code == "EMPTY_FEATURE_TEXT"
