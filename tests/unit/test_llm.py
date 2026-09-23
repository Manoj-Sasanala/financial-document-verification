"""LLM-01 verification: explanation input schema.

DoD: Schema is documented and serializable.
Test: Payload contains structured facts and retrieved evidence only.
"""

import json

import pytest

from app.llm.schemas import ExplanationInput, InputError, build_explanation_input


def _assembled():
    from app.document.field_parser import parse_fields as _parse
    from app.ml.inference import predict_case as _predict
    from app.rag.query_builder import build_query as _bq
    from app.rag.retriever import retrieve as _retrieve
    from app.verification.compare import compare_fields as _cmp
    from app.verification.normalize import normalize_fields as _nf
    from app.verification.risk_rules import assess_risk as _risk
    from app.verification.validate import validate_fields as _val

    text = (
        "Customer Name\nAarav Sharma\nAddress\n42 Example Avenue, Vijayawada\n"
        "Postal Code\n520001"
    )
    ref = {
        "customer_id": "CUST-0001",
        "customer_name": "Aarav Mehta",
        "address": "42 Example Avenue, Vijayawada",
        "postal_code": "520001",
    }
    normalized = _nf(_parse(text).fields)
    findings = _val(normalized)
    comparisons = _cmp(normalized, ref)
    indicators = _risk(findings, comparisons)
    ml_result = _predict(comparisons, indicators, findings)
    evidence = _retrieve(_bq(indicators, comparisons))
    return build_explanation_input(
        "CASE-LLM01",
        findings,
        comparisons,
        indicators,
        ml_classification=ml_result,
        policy_evidence=evidence,
    )


def test_payload_contains_facts_and_evidence_only() -> None:
    payload = _assembled()
    dumped = payload.model_dump()

    assert set(dumped.keys()) == {
        "schema_version",
        "case_id",
        "findings",
        "comparisons",
        "indicators",
        "ml_classification",
        "policy_evidence",
    }
    assert dumped["case_id"] == "CASE-LLM01"
    assert dumped["indicators"][0]["indicator_code"] == "name_mismatch"
    assert dumped["policy_evidence"]["status"] == "evidence_found"
    assert dumped["ml_classification"]["classification"] in {
        "consistent",
        "mismatch_detected",
        "insufficient_evidence",
    }


def test_payload_is_serializable() -> None:
    payload = _assembled()

    round_tripped = ExplanationInput.model_validate(json.loads(payload.model_dump_json()))

    assert round_tripped == payload


def test_payload_rejects_undeclared_content() -> None:
    with pytest.raises(Exception):
        ExplanationInput(
            case_id="X",
            findings=[],
            comparisons=[],
            indicators=[],
            raw_document_text="should not be allowed",
        )


def test_empty_case_id_is_explicit() -> None:
    with pytest.raises(InputError) as exc_info:
        build_explanation_input("  ", [], [], [])
    assert exc_info.value.code == "EMPTY_CASE_ID"


def test_wrong_record_types_are_explicit() -> None:
    with pytest.raises(InputError) as exc_info:
        build_explanation_input("X", ["nope"], [], [])
    assert exc_info.value.code == "INVALID_RECORD"
