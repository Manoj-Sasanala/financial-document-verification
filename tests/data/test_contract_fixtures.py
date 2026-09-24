"""L1 canonical cross-lane fixture validation for frozen C01-C04 contracts."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "data" / "fixtures" / "contracts"

C01 = {
    "document_result.clean.json",
    "document_result_missing_field.json",
    "document_result_ocr_warning.json",
    "document_result_failed.json",
}
C02 = {
    "verification_result.clean.json",
    "verification_result_name_mismatch.json",
    "verification_result_address_mismatch.json",
    "verification_result_missing_invalid.json",
    "verification_result_unknown_customer.json",
    "verification_result_unsupported_document.json",
}
C03 = {
    "ml_result_consistent.json",
    "ml_result_mismatch.json",
    "ml_result_insufficient.json",
    "ml_result_failed.json",
}
C04 = {
    "rag_result_evidence.json",
    "rag_result_no_evidence.json",
    "rag_result_failed.json",
}


def load(name: str) -> dict:
    path = FIXTURE_DIR / name
    assert path.is_file(), f"missing canonical fixture: {path}"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def assert_c09_error(error: dict, allowed_stages: set[str]) -> None:
    assert set(error) == {"contract_id", "stage", "code", "message", "retryable", "fatal", "details"}
    assert error["contract_id"] == "C09"
    assert error["stage"] in allowed_stages
    assert isinstance(error["code"], str) and error["code"]
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["retryable"], bool)
    assert isinstance(error["fatal"], bool)
    assert isinstance(error["details"], dict)


def test_all_required_c01_to_c04_fixtures_exist() -> None:
    required = C01 | C02 | C03 | C04
    assert {p.name for p in FIXTURE_DIR.glob("*.json")} >= required


def test_c01_fixture_shapes_and_failure_states() -> None:
    required = {"contract_id", "case_id", "customer_id", "status", "document_type", "fields", "warnings", "error"}
    field_names = {"customer_name", "address", "document_type", "document_date", "issuer_name", "document_number", "postal_code"}
    for name in C01:
        item = load(name)
        assert set(item) >= required
        assert item["contract_id"] == "C01"
        assert item["status"] in {"processing", "completed", "completed_with_warnings", "failed"}
        assert set(item["fields"]) == field_names
        for field in item["fields"].values():
            assert set(field) == {"raw", "value", "status"}
            assert field["status"] in {"present", "missing", "uncertain"}
        if item["status"] == "failed":
            assert item["extracted_text"] is None
            assert item["error"] is not None
            assert_c09_error(item["error"], {"extraction"})
        else:
            assert item["error"] is None


def test_c02_fixture_shapes_cover_deterministic_scenarios() -> None:
    required = {"contract_id", "case_id", "status", "normalized_fields", "validation_findings", "comparison_findings", "risk_indicators", "deterministic_status", "rule_version", "error"}
    expected_rules = {
        "RISK-NAME-MISMATCH", "RISK-ADDRESS-MISMATCH", "RISK-MISSING-FIELD",
        "RISK-INVALID-DATE", "RISK-CUSTOMER-NOT-FOUND", "RISK-UNSUPPORTED-DOCUMENT",
    }
    for name in C02:
        item = load(name)
        assert set(item) == required
        assert item["contract_id"] == "C02"
        assert item["status"] in {"processing", "completed", "completed_with_warnings", "failed"}
        assert item["deterministic_status"] in {"verified", "attention_required", "insufficient_evidence"}
        for finding in item["validation_findings"]:
            assert set(finding) == {"field", "code", "message", "severity"}
            assert finding["severity"] in {"warning", "error"}
        for finding in item["comparison_findings"]:
            assert set(finding) == {"field", "result", "reference_value", "observed_value", "reason"}
            assert finding["result"] in {"match", "mismatch", "missing", "unavailable"}
        for indicator in item["risk_indicators"]:
            assert set(indicator) == {"rule_id", "category", "severity", "reason", "affected_field"}
            assert indicator["rule_id"] in expected_rules
            assert indicator["severity"] in {"low", "medium", "high"}
        assert item["error"] is None


def test_c03_fixture_shapes_cover_all_advisory_classes_and_failure() -> None:
    required = {"contract_id", "case_id", "status", "class", "model_version", "error"}
    classes = set()
    for name in C03:
        item = load(name)
        assert set(item) >= required
        assert item["contract_id"] == "C03"
        assert item["status"] in {"completed", "completed_with_warnings", "failed"}
        if item["status"] == "failed":
            assert item["class"] is None
            assert item["error"] is not None
            assert_c09_error(item["error"], {"ml"})
        else:
            assert item["class"] in {"consistent", "mismatch_detected", "insufficient_evidence"}
            classes.add(item["class"])
            assert item["error"] is None
        assert item["model_version"]
    assert classes == {"consistent", "mismatch_detected", "insufficient_evidence"}


def test_c04_fixture_shapes_preserve_controlled_policy_identity() -> None:
    required = {"contract_id", "case_id", "status", "evidence", "error"}
    for name in C04:
        item = load(name)
        assert set(item) == required
        assert item["contract_id"] == "C04"
        assert item["status"] in {"completed", "no_evidence", "completed_with_warnings", "failed"}
        for evidence in item["evidence"]:
            assert {"source_id", "version", "chunk_id", "text"} <= set(evidence)
            assert evidence["source_id"].startswith("POL-RISK-")
            assert evidence["version"] == "1.0.0"
            assert evidence["chunk_id"].startswith(f"{evidence['source_id']}#chunk-")
            assert evidence["text"]
        if item["status"] == "failed":
            assert item["error"] is not None
            assert_c09_error(item["error"], {"rag"})
        else:
            assert item["error"] is None


def test_fixtures_are_synthetic_and_secret_free() -> None:
    raw = "\n".join(p.read_text(encoding="utf-8") for p in FIXTURE_DIR.glob("*.json"))
    for forbidden in ("sk-live-", "AKIA[0-9A-Z]{8}", "BEGIN PRIVATE KEY", "password=", "@gmail.com", "@yahoo.com"):
        assert forbidden.lower() not in raw.lower()
