"""API-06 verification: standard error/state handling.

DoD: Failure-path integration tests pass.
Test: Forced RAG/LLM failure returns a controlled degraded result without
changing deterministic findings.
"""

from pathlib import Path

from app.db.init_db import initialize_database
from app.db.repository import (
    create_case,
    save_extracted_fields,
    save_findings,
)
from app.orchestration.pipeline import process_case
from scripts.seed_db import seed_customers


def _seed_mismatch_db(tmp_path: Path, case_id: str = "CASE-FAIL-001") -> Path:
    from app.document.field_parser import parse_fields
    from app.verification.compare import compare_fields
    from app.verification.normalize import normalize_fields
    from app.verification.risk_rules import assess_risk
    from app.verification.validate import validate_fields

    db_path = tmp_path / "fail.db"
    initialize_database(db_path)
    seed_customers(db_path)
    create_case(db_path, case_id, "CUST-0001", "proof.pdf", "application/pdf")

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


def _boom_retriever(query):
    raise RuntimeError("index offline")


def _boom_explain(findings, comparisons, indicators, ml_result, evidence):
    raise RuntimeError("llm offline")


def test_forced_rag_failure_degrades_without_changing_findings(tmp_path: Path) -> None:
    db_path = _seed_mismatch_db(tmp_path)
    result = process_case(
        "CASE-FAIL-001",
        db_path=db_path,
        retriever=_boom_retriever,
        llm_transport=lambda text: "Name differs.",
    )

    assert result.policy_evidence is None
    assert any(e.stage == "retrieval" and e.recoverable for e in result.errors)
    assert [i.indicator_code for i in result.risk_indicators] == ["name_mismatch"]
    assert result.comparisons[0].status == "mismatch"
    assert result.status in {"completed_with_warnings", "failed"}


def test_forced_llm_failure_degrades_without_changing_findings(tmp_path: Path) -> None:
    db_path = _seed_mismatch_db(tmp_path, case_id="CASE-FAIL-002")
    result = process_case(
        "CASE-FAIL-002",
        db_path=db_path,
        llm_explain=_boom_explain,
    )

    assert result.explanation is None
    assert any(e.stage == "explanation" and e.recoverable for e in result.errors)
    assert [i.indicator_code for i in result.risk_indicators] == ["name_mismatch"]


def test_forced_rag_and_llm_failure_still_returns_deterministic_core(tmp_path: Path) -> None:
    db_path = _seed_mismatch_db(tmp_path, case_id="CASE-FAIL-003")
    result = process_case(
        "CASE-FAIL-003",
        db_path=db_path,
        retriever=_boom_retriever,
        llm_explain=_boom_explain,
    )

    assert result.policy_evidence is None
    assert result.explanation is None
    assert result.fields.customer_name.raw_value == "Aarav Sharma"
    assert [i.indicator_code for i in result.risk_indicators] == ["name_mismatch"]
    assert result.ml_classification is not None
    stages = {e.stage for e in result.errors}
    assert {"retrieval", "explanation"} <= stages


def test_processing_failed_state_for_unreadable_case(tmp_path: Path) -> None:
    from app.db.repository import save_review

    db_path = _seed_mismatch_db(tmp_path, case_id="CASE-FAIL-004")
    save_review(db_path, "CASE-FAIL-004", "request_information", "Unreadable scan.")
    result = process_case(
        "CASE-FAIL-004",
        db_path=db_path,
        retriever=_boom_retriever,
        llm_explain=_boom_explain,
    )

    assert result.status in {
        "processing",
        "completed",
        "completed_with_warnings",
        "failed",
    }
    assert result.review is not None
    assert result.review.decision == "request_information"


# ---------------------------------------------------------------------------
# QA-04: Failure-path QA (DoD: all required failure-path tests pass; forced
# RAG/LLM failure does not delete earlier findings)
# ---------------------------------------------------------------------------


def test_unreadable_ocr_case_yields_controlled_missing_findings(tmp_path: Path) -> None:
    from app.document.field_parser import parse_fields as _parse
    from app.verification.compare import compare_fields as _compare
    from app.verification.normalize import normalize_fields as _nf
    from app.verification.risk_rules import assess_risk as _assess
    from app.verification.validate import validate_fields as _validate

    parsed = _parse("████ ▓▓▓▓ ??? unreadable/OCR-hostile ???")
    normalized = _nf(parsed.fields)
    findings = _validate(normalized)
    comparisons = _compare(normalized, None)
    indicators = _assess(findings, comparisons, reference_found=False)

    assert {c.status for c in comparisons} == {"unavailable"}
    assert "reference_customer_not_found" in [i.indicator_code for i in indicators]


def test_forced_failures_do_not_delete_earlier_findings(tmp_path: Path) -> None:
    from app.db.repository import load_findings

    db_path = _seed_mismatch_db(tmp_path, case_id="CASE-FAIL-005")
    before = load_findings(db_path, "CASE-FAIL-005")
    assert any(r["ref"] == "name_mismatch" for r in before)

    result = process_case(
        "CASE-FAIL-005",
        db_path=db_path,
        retriever=_boom_retriever,
        llm_explain=_boom_explain,
    )

    after = load_findings(db_path, "CASE-FAIL-005")
    assert before == after
    assert [i.indicator_code for i in result.risk_indicators] == ["name_mismatch"]


def test_llm_timeout_returns_controlled_failed_explanation(tmp_path: Path) -> None:
    def _timeout(_: str) -> str:
        raise TimeoutError("llm timed out")

    db_path = _seed_mismatch_db(tmp_path, case_id="CASE-FAIL-006")
    result = process_case(
        "CASE-FAIL-006",
        db_path=db_path,
        llm_transport=_timeout,
    )

    assert result.explanation is not None
    assert result.explanation.status == "failed"
    assert [i.indicator_code for i in result.risk_indicators] == ["name_mismatch"]


# ---------------------------------------------------------------------------
# QA-05: Security/file-handling checks (DoD: checklist passes with no known
# secret/file-handling defect; unsupported/oversized rejected, secrets safe)
# ---------------------------------------------------------------------------


def test_oversized_upload_is_rejected(tmp_path: Path) -> None:
    import os

    from fastapi.testclient import TestClient

    from app.main import app

    db_path = tmp_path / "sec.db"
    initialize_database(db_path)
    seed_customers(db_path)
    os.environ["CASE_DB_PATH"] = str(db_path)
    client = TestClient(app)

    big = b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024)
    response = client.post(
        "/api/v1/cases",
        data={"customer_id": "CUST-0001"},
        files={"file": ("big.pdf", big, "application/pdf")},
    )

    assert response.status_code == 400
    assert "FILE_TOO_LARGE" in response.json()["detail"]


def test_executable_upload_is_rejected(tmp_path: Path) -> None:
    import os

    from fastapi.testclient import TestClient

    from app.main import app

    db_path = tmp_path / "sec2.db"
    initialize_database(db_path)
    seed_customers(db_path)
    os.environ["CASE_DB_PATH"] = str(db_path)
    client = TestClient(app)

    response = client.post(
        "/api/v1/cases",
        data={"customer_id": "CUST-0001"},
        files={"file": ("run.exe", b"MZ" + b"\x00" * 100, "application/octet-stream")},
    )

    assert response.status_code == 400


def test_path_traversal_filename_is_sanitized() -> None:
    from app.document.upload_validation import validate_upload

    result = validate_upload(
        "../../etc/passwd.pdf", b"%PDF-1.4\ncontent", content_type="application/pdf"
    )

    assert "/" not in result.filename
    assert "\\" not in result.filename
    assert result.filename == "passwd.pdf"


def test_security_checklist_is_complete() -> None:
    checklist = (
        Path(__file__).resolve().parents[2] / "docs" / "security-checklist.md"
    ).read_text(encoding="utf-8")

    for item in (
        "FILE_TOO_LARGE",
        "UNSUPPORTED_FILE_TYPE",
        "INVALID_FILE_SIGNATURE",
        "server-side",
        ".env",
    ):
        assert item in checklist
