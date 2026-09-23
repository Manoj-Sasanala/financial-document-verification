"""DATA-06: Prepare ML labeled cases.

Builds the small supervised dataset for case classification from the
DATA-04 and DATA-05 scenarios.

Outputs (canonical storage, per repo file-structure map):
  data/ml/train.jsonl
  data/ml/test.jsonl
(one labeled example per line; file-level counts derived, provenance per example)

Label contract (frozen Step 9.6 / Step 6, see app/core/contracts.py MLResult):
  consistent | mismatch_detected | insufficient_evidence

Mapping (deterministic boundary):
  clean                                        -> consistent
  name_mismatch, address_mismatch              -> mismatch_detected
  missing_field, invalid_date,
  unsupported_document, unknown_customer,
  unreadable_ocr                               -> insufficient_evidence

Guarantees:
  * All three classes are represented in BOTH train and test.
  * No exact example is reused across train and test (disjoint example_id
    AND disjoint (scenario_type, customer_id, variant) keys).
  * Synthetic-only data; no real customer information.
  * Deterministic: fixed ordering, no randomness, no timestamps in examples.
  * Provenance preserved per example + per file.

Consumer: ML training pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CUSTOMERS_PATH = PROJECT_ROOT / "data" / "synthetic" / "customers.json"
SCENARIOS_PATH = PROJECT_ROOT / "data" / "synthetic" / "scenarios.json"

ML_DIR = PROJECT_ROOT / "data" / "ml"
TRAIN_PATH = ML_DIR / "train.jsonl"
TEST_PATH = ML_DIR / "test.jsonl"

SCHEMA_VERSION = "1.0.0"
GENERATOR_VERSION = "1.0.0"
TASK_ID = "DATA-06"

Label = Literal["consistent", "mismatch_detected", "insufficient_evidence"]

ALLOWED_LABELS: tuple[Label, Label, Label] = (
    "consistent",
    "mismatch_detected",
    "insufficient_evidence",
)

# scenario_type -> label (deterministic boundary, frozen for DATA-06)
SCENARIO_TO_LABEL: dict[str, Label] = {
    "clean": "consistent",
    "name_mismatch": "mismatch_detected",
    "address_mismatch": "mismatch_detected",
    "missing_field": "insufficient_evidence",
    "invalid_date": "insufficient_evidence",
    "unsupported_document": "insufficient_evidence",
    "unknown_customer": "insufficient_evidence",
    "unreadable_ocr": "insufficient_evidence",
}

# scenario_type -> source scenario_id in scenarios.json (DATA-04/DATA-05)
SCENARIO_TO_SOURCE: dict[str, str] = {
    "clean": "DATA-04-CLEAN-001",
    "name_mismatch": "DATA-04-NAME-001",
    "address_mismatch": "DATA-04-ADDRESS-001",
    "missing_field": "DATA-05-MISSING-ADDRESS-001",
    "invalid_date": "DATA-05-INVALID-DATE-001",
    "unsupported_document": "DATA-05-UNSUPPORTED-DOCUMENT-001",
    "unknown_customer": "DATA-05-UNKNOWN-CUSTOMER-001",
    "unreadable_ocr": "DATA-05-UNREADABLE-OCR-001",
}


class MLLabelError(ValueError):
    """Controlled DATA-06 failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise MLLabelError("FILE_NOT_FOUND", f"Required input not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise MLLabelError("INVALID_JSON", f"Invalid JSON in {path}: {exc}") from exc


def load_customers() -> dict[str, dict[str, str]]:
    customers = load_json(CUSTOMERS_PATH)
    if not isinstance(customers, list) or not customers:
        raise MLLabelError("INVALID_CUSTOMERS", "customers.json must be a non-empty list")
    by_id: dict[str, dict[str, str]] = {}
    for cust in customers:
        if not isinstance(cust, dict) or "customer_id" not in cust:
            raise MLLabelError("INVALID_CUSTOMERS", "Each customer must have a customer_id")
        by_id[str(cust["customer_id"])] = {k: str(v) for k, v in cust.items()}
    return by_id


def validate_scenarios_available(scenarios_data: dict[str, Any]) -> None:
    scenarios = scenarios_data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise MLLabelError("INVALID_SCENARIOS", "scenarios.json must contain a non-empty scenarios list")
    ids = {s.get("scenario_id") for s in scenarios if isinstance(s, dict)}
    missing = [sid for sid in SCENARIO_TO_SOURCE.values() if sid not in ids]
    if missing:
        raise MLLabelError(
            "MISSING_SCENARIOS",
            f"DATA-04/DATA-05 scenarios missing from scenarios.json: {missing}",
        )


def build_features(
    scenario_type: str,
    reference: dict[str, str],
    observed: dict[str, str],
) -> dict[str, int | list[str]]:
    """Deterministic feature flags derived from reference vs observed."""
    if scenario_type == "clean":
        return {
            "name_match": 1,
            "address_match": 1,
            "postal_match": 1,
            "has_missing_field": 0,
            "has_invalid_date": 0,
            "is_unsupported_document": 0,
            "is_unknown_customer": 0,
            "is_unreadable": 0,
            "num_mismatched_fields": 0,
            "mismatch_fields": [],
        }
    if scenario_type == "name_mismatch":
        return {
            "name_match": 0,
            "address_match": 1,
            "postal_match": 1,
            "has_missing_field": 0,
            "has_invalid_date": 0,
            "is_unsupported_document": 0,
            "is_unknown_customer": 0,
            "is_unreadable": 0,
            "num_mismatched_fields": 1,
            "mismatch_fields": ["customer_name"],
        }
    if scenario_type == "address_mismatch":
        return {
            "name_match": 1,
            "address_match": 0,
            "postal_match": 1,
            "has_missing_field": 0,
            "has_invalid_date": 0,
            "is_unsupported_document": 0,
            "is_unknown_customer": 0,
            "is_unreadable": 0,
            "num_mismatched_fields": 1,
            "mismatch_fields": ["address"],
        }
    if scenario_type == "missing_field":
        return {
            "name_match": 1,
            "address_match": 0,
            "postal_match": 1,
            "has_missing_field": 1,
            "has_invalid_date": 0,
            "is_unsupported_document": 0,
            "is_unknown_customer": 0,
            "is_unreadable": 0,
            "num_mismatched_fields": 1,
            "mismatch_fields": ["address"],
        }
    if scenario_type == "invalid_date":
        return {
            "name_match": 1,
            "address_match": 1,
            "postal_match": 1,
            "has_missing_field": 0,
            "has_invalid_date": 1,
            "is_unsupported_document": 0,
            "is_unknown_customer": 0,
            "is_unreadable": 0,
            "num_mismatched_fields": 0,
            "mismatch_fields": [],
        }
    if scenario_type == "unsupported_document":
        return {
            "name_match": 1,
            "address_match": 1,
            "postal_match": 1,
            "has_missing_field": 0,
            "has_invalid_date": 0,
            "is_unsupported_document": 1,
            "is_unknown_customer": 0,
            "is_unreadable": 0,
            "num_mismatched_fields": 0,
            "mismatch_fields": [],
        }
    if scenario_type == "unknown_customer":
        return {
            "name_match": 0,
            "address_match": 0,
            "postal_match": 0,
            "has_missing_field": 0,
            "has_invalid_date": 0,
            "is_unsupported_document": 0,
            "is_unknown_customer": 1,
            "is_unreadable": 0,
            "num_mismatched_fields": 3,
            "mismatch_fields": ["customer_name", "address", "postal_code"],
        }
    if scenario_type == "unreadable_ocr":
        return {
            "name_match": 0,
            "address_match": 0,
            "postal_match": 0,
            "has_missing_field": 0,
            "has_invalid_date": 0,
            "is_unsupported_document": 0,
            "is_unknown_customer": 0,
            "is_unreadable": 1,
            "num_mismatched_fields": 0,
            "mismatch_fields": [],
        }
    raise MLLabelError("UNKNOWN_SCENARIO_TYPE", f"Unknown scenario_type: {scenario_type}")


def build_observed(
    scenario_type: str,
    reference: dict[str, str],
    customer_id: str,
) -> dict[str, str]:
    """Deterministic observed values per scenario type (synthetic-only)."""
    if scenario_type == "clean":
        return dict(reference)
    if scenario_type == "name_mismatch":
        obs = dict(reference)
        obs["customer_name"] = "Aarav Sharma"
        return obs
    if scenario_type == "address_mismatch":
        obs = dict(reference)
        obs["address"] = "99 Synthetic Street, Vijayawada"
        return obs
    if scenario_type == "missing_field":
        obs = dict(reference)
        obs["address"] = ""
        return obs
    if scenario_type == "invalid_date":
        obs = dict(reference)
        obs["document_date"] = "2026-02-30"
        return obs
    if scenario_type == "unsupported_document":
        obs = dict(reference)
        obs["document_type"] = "utility_service_notice"
        return obs
    if scenario_type == "unknown_customer":
        return {
            "customer_id": "CUST-9999",
            "customer_name": "Synthetic Unknown Customer",
            "address": "1 Synthetic Unknown Street, Vijayawada",
            "postal_code": "520999",
        }
    if scenario_type == "unreadable_ocr":
        return {
            "customer_id": reference.get("customer_id", customer_id),
            "customer_name": "████▓▓▓▓ ???",
            "address": "████▓▓▓▓ ???",
            "postal_code": "???",
        }
    raise MLLabelError("UNKNOWN_SCENARIO_TYPE", f"Unknown scenario_type: {scenario_type}")


def make_example(
    example_id: str,
    split: str,
    scenario_type: str,
    customer_id: str,
    customers: dict[str, dict[str, str]],
) -> dict[str, Any]:
    if scenario_type not in SCENARIO_TO_LABEL:
        raise MLLabelError("UNKNOWN_SCENARIO_TYPE", f"Unknown scenario_type: {scenario_type}")
    label = SCENARIO_TO_LABEL[scenario_type]
    source_scenario_id = SCENARIO_TO_SOURCE[scenario_type]

    if scenario_type == "unknown_customer":
        # Reference lookup intentionally fails; use CUST-0001 shape as the
        # requested-but-absent reference context without inventing a record.
        reference_base = customers.get("CUST-0001")
        if reference_base is None:
            raise MLLabelError("MISSING_REFERENCE", "CUST-0001 required as reference context")
        reference = {
            "customer_id": "CUST-9999",
            "customer_name": reference_base["customer_name"],
            "address": reference_base["address"],
            "postal_code": reference_base["postal_code"],
        }
    else:
        if customer_id not in customers:
            raise MLLabelError("UNKNOWN_CUSTOMER", f"Unknown customer_id: {customer_id}")
        cust = customers[customer_id]
        reference = {
            "customer_id": cust["customer_id"],
            "customer_name": cust["customer_name"],
            "address": cust["address"],
            "postal_code": cust["postal_code"],
        }

    observed = build_observed(scenario_type, reference, customer_id)
    features = build_features(scenario_type, reference, observed)

    return {
        "example_id": example_id,
        "split": split,
        "label": label,
        "scenario_type": scenario_type,
        "source_scenario_id": source_scenario_id,
        "customer_id": observed.get("customer_id", customer_id),
        "reference_customer_id": customer_id if scenario_type != "unknown_customer" else None,
        "features": features,
        "reference": reference,
        "observed": observed,
        "provenance": {
            "task_id": TASK_ID,
            "schema_version": SCHEMA_VERSION,
            "generator_version": GENERATOR_VERSION,
            "source_scenarios": "data/synthetic/scenarios.json",
            "source_customer_file": "data/synthetic/customers.json",
            "source_scenario_id": source_scenario_id,
            "synthetic_only": True,
        },
    }


# Fixed, deterministic split plan.
# No (scenario_type, customer/variant) key is reused across train and test.
# Train: 9 examples (3 per class). Test: 6 examples (2 per class).
TRAIN_PLAN: list[tuple[str, str, str]] = [
    # (example_id, scenario_type, customer_id)
    ("DATA-06-TRAIN-001", "clean", "CUST-0001"),
    ("DATA-06-TRAIN-002", "clean", "CUST-0002"),
    ("DATA-06-TRAIN-003", "clean", "CUST-0003"),
    ("DATA-06-TRAIN-004", "name_mismatch", "CUST-0001"),
    ("DATA-06-TRAIN-005", "address_mismatch", "CUST-0001"),
    ("DATA-06-TRAIN-006", "name_mismatch", "CUST-0002"),
    ("DATA-06-TRAIN-007", "missing_field", "CUST-0001"),
    ("DATA-06-TRAIN-008", "invalid_date", "CUST-0001"),
    ("DATA-06-TRAIN-009", "unreadable_ocr", "CUST-0001"),
]

TEST_PLAN: list[tuple[str, str, str]] = [
    ("DATA-06-TEST-001", "clean", "CUST-0004"),
    ("DATA-06-TEST-002", "clean", "CUST-0005"),
    ("DATA-06-TEST-003", "address_mismatch", "CUST-0002"),
    ("DATA-06-TEST-004", "name_mismatch", "CUST-0003"),
    ("DATA-06-TEST-005", "unsupported_document", "CUST-0001"),
    ("DATA-06-TEST-006", "unknown_customer", "CUST-9999"),
]


def build_split(
    split: str,
    plan: list[tuple[str, str, str]],
    customers: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for example_id, scenario_type, customer_id in plan:
        examples.append(make_example(example_id, split, scenario_type, customer_id, customers))
    return examples


def validate_no_reuse(
    train_examples: list[dict[str, Any]],
    test_examples: list[dict[str, Any]],
) -> None:
    train_ids = [e["example_id"] for e in train_examples]
    test_ids = [e["example_id"] for e in test_examples]
    if len(set(train_ids)) != len(train_ids):
        raise MLLabelError("DUPLICATE_IDS", "Duplicate example_id within train split")
    if len(set(test_ids)) != len(test_ids):
        raise MLLabelError("DUPLICATE_IDS", "Duplicate example_id within test split")
    overlap = set(train_ids) & set(test_ids)
    if overlap:
        raise MLLabelError("SPLIT_LEAKAGE", f"example_id reused across train/test: {sorted(overlap)}")

    def dedup_key(e: dict[str, Any]) -> tuple[str, str, str]:
        return (str(e["scenario_type"]), str(e["observed"].get("customer_id")), str(e["label"]))

    train_keys = {dedup_key(e) for e in train_examples}
    test_keys = {dedup_key(e) for e in test_examples}
    key_overlap = train_keys & test_keys
    if key_overlap:
        raise MLLabelError(
            "SPLIT_LEAKAGE",
            f"Exact (scenario_type, observed customer, label) reused across splits: {sorted(key_overlap)}",
        )

    # Full-payload comparison: no identical example dict may appear twice.
    train_payloads = {json.dumps(e, sort_keys=True) for e in train_examples}
    test_payloads = {json.dumps(e, sort_keys=True) for e in test_examples}
    if train_payloads & test_payloads:
        raise MLLabelError("SPLIT_LEAKAGE", "Identical example payload present in both splits")


def validate_class_coverage(examples: list[dict[str, Any]], split: str) -> None:
    labels = {e["label"] for e in examples}
    missing = set(ALLOWED_LABELS) - labels
    if missing:
        raise MLLabelError(
            "MISSING_CLASS",
            f"Split '{split}' is missing classes: {sorted(missing)}",
        )
    for e in examples:
        if e["label"] not in ALLOWED_LABELS:
            raise MLLabelError("INVALID_LABEL", f"Invalid label {e['label']!r} in {e['example_id']}")


def write_dataset(path: Path, split: str, examples: list[dict[str, Any]]) -> None:
    """Write one labeled example per line (JSONL, deterministic order)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for example in examples:
            fh.write(json.dumps(example, sort_keys=False) + "\n")


def read_dataset(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL dataset (one example per line); skips blank lines."""
    if not path.is_file():
        raise MLLabelError("FILE_NOT_FOUND", f"Required dataset not found: {path}")
    examples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MLLabelError(
                    "INVALID_JSONL", f"Invalid JSON on line {lineno} of {path}: {exc}"
                ) from exc
            if not isinstance(obj, dict):
                raise MLLabelError(
                    "INVALID_EXAMPLE", f"Line {lineno} of {path} must be a JSON object"
                )
            examples.append(obj)
    if not examples:
        raise MLLabelError("EMPTY_DATASET", f"Dataset is empty: {path}")
    return examples


def main() -> None:
    customers = load_customers()
    scenarios_data = load_json(SCENARIOS_PATH)
    if not isinstance(scenarios_data, dict):
        raise MLLabelError("INVALID_SCENARIOS", "scenarios.json must contain a JSON object")
    validate_scenarios_available(scenarios_data)

    train_examples = build_split("train", TRAIN_PLAN, customers)
    test_examples = build_split("test", TEST_PLAN, customers)

    validate_class_coverage(train_examples, "train")
    validate_class_coverage(test_examples, "test")
    validate_no_reuse(train_examples, test_examples)

    write_dataset(TRAIN_PATH, "train", train_examples)
    write_dataset(TEST_PATH, "test", test_examples)

    print(f"Wrote {len(train_examples)} train examples -> {TRAIN_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"Wrote {len(test_examples)} test examples -> {TEST_PATH.relative_to(PROJECT_ROOT).as_posix()}")
    print(f"Train labels: {{e['label'] for e in train}} = {sorted({e['label'] for e in train_examples})}")
    print(f"Test labels: {sorted({e['label'] for e in test_examples})}")


if __name__ == "__main__":
    main()
