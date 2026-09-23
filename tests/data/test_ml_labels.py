"""DATA-06 verification: ML labeled cases.

DoD: Labeled files are loadable and class labels match the Step 6 contract.
Test: Classes are represented in both datasets without reusing the same
exact examples across train and test.
"""

import json
from pathlib import Path

from app.core.contracts import MLResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAIN_PATH = PROJECT_ROOT / "data" / "synthetic" / "ml" / "train.json"
TEST_PATH = PROJECT_ROOT / "data" / "synthetic" / "ml" / "test.json"
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


def load_dataset(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_train_and_test_files_exist_and_load() -> None:
    assert TRAIN_PATH.is_file(), f"Missing {TRAIN_PATH}"
    assert TEST_PATH.is_file(), f"Missing {TEST_PATH}"
    train = load_dataset(TRAIN_PATH)
    test = load_dataset(TEST_PATH)
    assert isinstance(train["examples"], list) and train["examples"]
    assert isinstance(test["examples"], list) and test["examples"]


def test_file_metadata_matches_data06_contract() -> None:
    for path, split in ((TRAIN_PATH, "train"), (TEST_PATH, "test")):
        data = load_dataset(path)
        assert data["task_id"] == "DATA-06"
        assert data["split"] == split
        assert data["synthetic_only"] is True
        assert set(data["label_contract"]) == ALLOWED_LABELS
        assert data["num_examples"] == len(data["examples"])
        assert data["source_scenarios"] == "data/synthetic/scenarios.json"
        assert data["source_customer_file"] == "data/synthetic/customers.json"


def test_labels_match_step6_mlresult_contract() -> None:
    for path in (TRAIN_PATH, TEST_PATH):
        data = load_dataset(path)
        for example in data["examples"]:
            assert example["label"] in ALLOWED_LABELS
            # Frozen Step 9.6 / Step 6 contract: MLResult must accept the label.
            result = MLResult(classification=example["label"], model_version="test")
            assert result.classification == example["label"]


def test_all_classes_represented_in_both_splits() -> None:
    train_labels = {e["label"] for e in load_dataset(TRAIN_PATH)["examples"]}
    test_labels = {e["label"] for e in load_dataset(TEST_PATH)["examples"]}
    assert train_labels == ALLOWED_LABELS, f"train missing {ALLOWED_LABELS - train_labels}"
    assert test_labels == ALLOWED_LABELS, f"test missing {ALLOWED_LABELS - test_labels}"


def test_no_exact_examples_reused_across_splits() -> None:
    train = load_dataset(TRAIN_PATH)["examples"]
    test = load_dataset(TEST_PATH)["examples"]

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
        for example in load_dataset(path)["examples"]:
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
        for example in load_dataset(path)["examples"]:
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
