"""API-04 verification: orchestrator shell.

DoD: Ordered pipeline wired without duplicated business logic.
Test: Orchestrator runs end to end and with mocked downstream modules.
"""

from pathlib import Path

import pytest

from app.core.contracts import (
    CaseResult,
    ExplanationResult,
    MLResult,
    RetrievalResult,
)
from app.db.init_db import initialize_database
from app.db.repository import (
    create_case,
    save_extracted_fields,
    save_findings,
)
from app.orchestration.pipeline import PipelineError, process_case
from scripts.seed_db import seed_customers


def _seed_case_db(tmp_path: Path, case_id: str = "CASE-PIPE-001") -> Path:
    from app.document.field_parser import parse_fields
    from app.verification.compare import compare_fields
    from app.verification.normalize import normalize_fields
    from app.verification.risk_rules import assess_risk
    from app.verification.validate import validate_fields

    db_path = tmp_path / "pipe.db"
    initialize_database(db_path)
    seed_customers(db_path)
    create_case(db_path, case_id, "CUST-0001", "proof.pdf", "application/pdf")

    text = (
        "Customer Name\nAarav Mehta\nAddress\n42 Example Avenue, Vijayawada\n"
        "Postal Code\n520001"
    )
    ref = {
        "customer_id": "CUST-0001",
        "customer_name": "Aarav Mehta",
        "address": "42 Example Avenue, Vijayawada",
        "postal_code": "520001",
    }
    normalized = normalize_fields(parse_fields(text).fields)
    findings = validate_fields(normalized)
    comparisons = compare_fields(normalized, ref)
    indicators = assess_risk(findings, comparisons)
    save_extracted_fields(db_path, case_id, normalized)
    save_findings(
        db_path, case_id, findings=findings,
        comparisons=comparisons, indicators=indicators,
    )
    return db_path


def test_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    db_path = _seed_case_db(tmp_path)
    result = process_case(
        "CASE-PIPE-001",
        db_path=db_path,
        llm_transport=lambda text: "All values match the reference customer.",
    )

    assert isinstance(result, CaseResult)
    assert result.case_id == "CASE-PIPE-001"
    assert result.status in {"completed", "completed_with_warnings", "failed"}
    assert result.fields.customer_name.raw_value == "Aarav Mehta"
    assert result.normalized_fields.postal_code.normalized_value == "520001"
    assert result.ml_classification is not None
    assert result.ml_classification.model_version
    assert result.policy_evidence is not None
    assert result.explanation is not None
    assert result.errors == [] or all(e.recoverable for e in result.errors)


def test_pipeline_runs_with_mocked_downstream(tmp_path: Path) -> None:
    def _mock_predict(comparisons, indicators, findings):
        return MLResult(classification="consistent", model_version="mock-1.0")

    def _mock_retrieve(query):
        return RetrievalResult(status="no_evidence", evidence=[])

    def _mock_explain(findings, comparisons, indicators, ml_result, evidence):
        return ExplanationResult(status="unavailable", explanation=None, evidence_refs=[])

    db_path = _seed_case_db(tmp_path, case_id="CASE-MOCK-001")
    result = process_case(
        "CASE-MOCK-001",
        db_path=db_path,
        ml_predict=_mock_predict,
        retriever=_mock_retrieve,
        llm_explain=_mock_explain,
    )

    assert result.ml_classification is not None
    assert result.ml_classification.model_version == "mock-1.0"
    assert result.policy_evidence is not None
    assert result.policy_evidence.status == "no_evidence"
    assert result.explanation is not None
    assert result.explanation.status == "unavailable"


def test_pipeline_missing_case_is_explicit(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    initialize_database(db_path)
    with pytest.raises(PipelineError):
        process_case("CASE-NOPE", db_path=db_path)


def test_pipeline_records_stage_errors_without_crashing(tmp_path: Path) -> None:
    def _boom_predict(comparisons, indicators, findings):
        raise RuntimeError("model down")

    db_path = _seed_case_db(tmp_path, case_id="CASE-ERR-001")
    result = process_case(
        "CASE-ERR-001",
        db_path=db_path,
        ml_predict=_boom_predict,
        llm_transport=lambda text: "ok",
    )

    assert result.ml_classification is None
    assert any(e.stage == "ml" and e.recoverable for e in result.errors)
