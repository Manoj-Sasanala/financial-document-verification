"""DEP-03 verification: demo cases and fallback.

DoD: Three cases validated on the exact demo build; fallback available.
Test: Each demo case reproducible from the final build.
"""

import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_PDF = PROJECT_ROOT / "data" / "demo" / "clean-proof.pdf"
FALLBACK_PDF = PROJECT_ROOT / "data" / "demo" / "fallback" / "clean-proof.pdf"


def test_demo_inputs_exist_with_fallback_copy() -> None:
    assert DEMO_PDF.is_file()
    assert FALLBACK_PDF.is_file()
    assert (
        hashlib.sha256(DEMO_PDF.read_bytes()).hexdigest()
        == hashlib.sha256(FALLBACK_PDF.read_bytes()).hexdigest()
    )


def test_demo_case_clean_reproduces() -> None:
    from app.document.field_parser import parse_fields
    from app.document.pdf_extract import extract_pdf_text
    from app.verification.compare import compare_fields
    from app.verification.normalize import normalize_fields
    from app.verification.risk_rules import assess_risk
    from app.verification.validate import validate_fields

    ref = {
        "customer_id": "CUST-0001",
        "customer_name": "Aarav Mehta",
        "address": "42 Example Avenue, Vijayawada",
        "postal_code": "520001",
    }
    text = extract_pdf_text(DEMO_PDF.read_bytes()).text
    normalized = normalize_fields(parse_fields(text).fields)
    indicators = assess_risk(
        validate_fields(normalized), compare_fields(normalized, ref)
    )

    assert indicators == []


def test_demo_case_name_mismatch_reproduces() -> None:
    from app.document.field_parser import parse_fields
    from app.verification.compare import compare_fields
    from app.verification.normalize import normalize_fields
    from app.verification.risk_rules import assess_risk
    from app.verification.validate import validate_fields

    ref = {
        "customer_id": "CUST-0001",
        "customer_name": "Aarav Mehta",
        "address": "42 Example Avenue, Vijayawada",
        "postal_code": "520001",
    }
    text = (
        "Customer Name\nAarav Sharma\nAddress\n42 Example Avenue, Vijayawada\n"
        "Postal Code\n520001"
    )
    normalized = normalize_fields(parse_fields(text).fields)
    indicators = assess_risk(
        validate_fields(normalized), compare_fields(normalized, ref)
    )

    assert [i.indicator_code for i in indicators] == ["name_mismatch"]


def test_demo_case_degraded_reproduces() -> None:
    from app.document.field_parser import parse_fields
    from app.verification.compare import compare_fields
    from app.verification.normalize import normalize_fields
    from app.verification.risk_rules import assess_risk
    from app.verification.validate import validate_fields

    normalized = normalize_fields(
        parse_fields("████ ▓▓▓▓ ??? unreadable/OCR-hostile ???").fields
    )
    comparisons = compare_fields(normalized, None)
    indicators = assess_risk(
        validate_fields(normalized), comparisons, reference_found=False
    )

    assert {c.status for c in comparisons} == {"unavailable"}
    assert "reference_customer_not_found" in [i.indicator_code for i in indicators]


def test_runbook_documents_all_cases_and_fallback() -> None:
    runbook = (PROJECT_ROOT / "docs" / "demo-runbook.md").read_text(encoding="utf-8")

    assert "data/demo/clean-proof.pdf" in runbook
    assert "data/demo/fallback/" in runbook
    assert "name_mismatch" in runbook
