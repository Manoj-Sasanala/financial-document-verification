"""UI-01 verification: upload/review page shell.

DoD: Upload request reaches the backend and handles validation errors.
Test: Page can send a valid multipart request (form contract matches the
API-05 endpoint, verified live via TestClient).
"""

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.init_db import initialize_database
from app.main import app
from scripts.seed_db import seed_customers

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = PROJECT_ROOT / "app" / "ui" / "templates" / "review.html"
JS_PATH = PROJECT_ROOT / "app" / "ui" / "static" / "app.js"
CSS_PATH = PROJECT_ROOT / "app" / "ui" / "static" / "app.css"


def _html() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


def test_shell_files_exist() -> None:
    assert HTML_PATH.is_file()
    assert JS_PATH.is_file()
    assert CSS_PATH.is_file()


def test_form_posts_valid_multipart_request() -> None:
    html = _html()

    assert 'action="/api/v1/cases"' in html
    assert 'method="post"' in html
    assert 'enctype="multipart/form-data"' in html
    assert 'name="customer_id"' in html
    assert 'name="file"' in html
    assert 'type="file"' in html


def test_client_script_wires_upload_and_errors() -> None:
    js = JS_PATH.read_text(encoding="utf-8")

    assert "FormData" in js
    assert "fetch(" in js
    assert "detail" in js
    assert CSS_PATH.read_text(encoding="utf-8").strip() != ""


def test_form_contract_matches_backend(tmp_path: Path) -> None:
    db_path = tmp_path / "ui.db"
    initialize_database(db_path)
    seed_customers(db_path)
    os.environ["CASE_DB_PATH"] = str(db_path)
    client = TestClient(app)

    pdf = (PROJECT_ROOT / "data" / "synthetic" / "documents" / "template.pdf").read_bytes()
    response = client.post(
        "/api/v1/cases",
        data={"customer_id": "CUST-0001"},
        files={"file": ("proof.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201

    bad = client.post(
        "/api/v1/cases",
        data={"customer_id": "CUST-0001"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert bad.status_code == 400
    assert "detail" in bad.json()


# ---------------------------------------------------------------------------
# UI-02: Field display (DoD: all configured fields visibly represented;
# clean and missing-field cases render correctly)
# ---------------------------------------------------------------------------

_CONFIGURED_FIELDS = [
    "customer_name",
    "address",
    "document_type",
    "document_date",
    "issuer_name",
    "document_number",
    "postal_code",
]


def test_fields_table_covers_all_configured_fields() -> None:
    html = _html()

    assert 'id="fields-table"' in html
    assert 'id="fields-body"' in html
    js = JS_PATH.read_text(encoding="utf-8")
    for name in _CONFIGURED_FIELDS:
        assert f'"{name}"' in js


def test_renderer_marks_missing_and_uncertain_states() -> None:
    js = JS_PATH.read_text(encoding="utf-8")

    assert "renderFields" in js
    assert "data-status" in js
    assert "normalized_value" in js
    assert "raw_value" in js


def test_clean_and_missing_payloads_fit_renderer(tmp_path: Path) -> None:
    from app.document.field_parser import parse_fields
    from app.verification.normalize import normalize_fields

    clean = normalize_fields(
        parse_fields("Customer Name\nAarav Mehta\nPostal Code\n520001").fields
    )
    missing = normalize_fields(parse_fields("Customer Name\nAarav Mehta").fields)

    for record in (clean, missing):
        dumped = record.model_dump()
        assert set(dumped.keys()) == set(_CONFIGURED_FIELDS)
    assert clean.model_dump()["postal_code"]["normalized_value"] == "520001"
    assert missing.model_dump()["address"]["status"] == "missing"
    assert missing.model_dump()["address"]["normalized_value"] is None


# ---------------------------------------------------------------------------
# UI-03: Comparisons and risk indicators (DoD: deterministic findings clearly
# distinguishable from AI outputs; mismatch cases show correct findings)
# ---------------------------------------------------------------------------


def test_comparison_and_indicator_sections_exist() -> None:
    html = _html()

    assert 'id="comparisons-table"' in html
    assert 'id="comparisons-body"' in html
    assert 'id="indicators-list"' in html
    assert html.count('badge deterministic') == 2


def test_renderer_covers_comparisons_and_indicators() -> None:
    js = JS_PATH.read_text(encoding="utf-8")

    assert "renderComparisons" in js
    assert "renderIndicators" in js
    assert "observed_value" in js
    assert "reference_value" in js
    assert "indicator_code" in js
    assert "rule_id" in js


def test_mismatch_payloads_fit_renderer() -> None:
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
    cases = {
        "name": "Customer Name\nAarav Sharma\nAddress\n42 Example Avenue, Vijayawada\nPostal Code\n520001",
        "address": "Customer Name\nAarav Mehta\nAddress\n99 Synthetic Street, Vijayawada\nPostal Code\n520001",
    }
    expected = {"name": "name_mismatch", "address": "address_mismatch"}
    for kind, text in cases.items():
        normalized = normalize_fields(parse_fields(text).fields)
        comparisons = compare_fields(normalized, ref)
        indicators = assess_risk(validate_fields(normalized), comparisons)
        codes = [i.indicator_code for i in indicators]
        assert codes == [expected[kind]]
        assert any(c.status == "mismatch" for c in comparisons)
        for comparison in comparisons:
            assert {"field_name", "status", "observed_value", "reference_value"} <= set(
                comparison.model_dump()
            )


# ---------------------------------------------------------------------------
# UI-04: ML/RAG/explanation display (DoD: AI visibly separated from
# deterministic findings; renders even when explanation is unavailable)
# ---------------------------------------------------------------------------


def test_ai_section_is_badged_advisory() -> None:
    html = _html()

    assert 'badge advisory' in html
    assert 'id="ai-ml"' in html
    assert 'id="ai-model"' in html
    assert 'id="ai-evidence"' in html
    assert 'id="ai-explanation"' in html
    assert 'id="ai-explanation-status"' in html


def test_renderer_covers_ai_layers() -> None:
    js = JS_PATH.read_text(encoding="utf-8")

    assert "renderAi" in js
    assert "ml_classification" in js
    assert "policy_evidence" in js
    assert "No explanation available." in js
    assert "No policy evidence retrieved." in js


def test_unavailable_explanation_still_fits_renderer() -> None:
    from app.core.contracts import ExplanationResult, MLResult, RetrievalResult

    ml = MLResult(classification="consistent", model_version="1.0.0")
    assert ml.classification in {"consistent", "mismatch_detected", "insufficient_evidence"}

    empty = RetrievalResult(status="no_evidence", evidence=[])
    assert empty.evidence == []

    missing = ExplanationResult(status="unavailable", explanation=None, evidence_refs=[])
    dumped = missing.model_dump()
    assert dumped["status"] == "unavailable"
    assert dumped["explanation"] is None
    assert set(dumped.keys()) == {"status", "explanation", "evidence_refs"}
