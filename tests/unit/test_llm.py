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


# ---------------------------------------------------------------------------
# LLM-02: Grounded explanation prompt (DoD: fixed payload renders the
# intended structure; prompt forbids unsupported facts, cites evidence)
# ---------------------------------------------------------------------------

from app.llm.prompt import (  # noqa: E402
    PROMPT_VERSION as _PROMPT_VERSION,
)
from app.llm.prompt import PromptError as _PromptError
from app.llm.prompt import build_prompt as _build_prompt


def test_fixed_payload_produces_intended_structure() -> None:
    from app.llm.prompt import PROMPT_VERSION_PATH as _PVP

    result = _build_prompt(_assembled())

    assert result.prompt_version == _PROMPT_VERSION == "1.0.0"
    assert "FACTS" in result.prompt_text
    assert "EVIDENCE" in result.prompt_text
    assert "comparison customer_name mismatch" in result.prompt_text
    assert "indicator name_mismatch RISK-001" in result.prompt_text
    assert result.evidence_refs
    assert all(r.startswith("POL-RISK-") and "#chunk-" in r for r in result.evidence_refs)
    assert _PVP.is_file()


def test_prompt_forbids_unsupported_facts() -> None:
    result = _build_prompt(_assembled())

    assert "NEVER invent policy rules, chunk IDs, field values, or rule IDs" in result.prompt_text
    assert "Use ONLY the structured facts" in result.prompt_text


def test_prompt_identifies_source_evidence() -> None:
    result = _build_prompt(_assembled())

    for ref in result.evidence_refs:
        assert f"[{ref}]" in result.prompt_text


def test_prompt_is_deterministic() -> None:
    assert _build_prompt(_assembled()).prompt_text == _build_prompt(_assembled()).prompt_text


def test_prompt_version_metadata_matches() -> None:
    import json as _json

    from app.llm.prompt import PROMPT_VERSION_PATH as _PVP

    record = _json.loads(_PVP.read_text(encoding="utf-8"))

    assert record["prompt_version"] == _PROMPT_VERSION
    assert record["input_schema_version"] == "1.0.0"
    assert len(record["template_sha256"]) == 64


def test_prompt_rejects_wrong_input() -> None:
    with pytest.raises(_PromptError) as exc_info:
        _build_prompt("not-a-payload")  # type: ignore[arg-type]
    assert exc_info.value.code == "INVALID_INPUT"
