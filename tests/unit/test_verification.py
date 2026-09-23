"""VER-01 verification: field normalization.

DoD: Normalization unit tests pass for all configured fields.
Test: Case/whitespace differences normalize consistently while material
differences remain different.
"""

import pytest

from app.core.contracts import ExtractedFields, FieldValue
from app.verification.normalize import (
    NormalizationError,
    normalize_address,
    normalize_document_date,
    normalize_fields,
    normalize_name,
    normalize_postal_code,
    normalize_value,
)


def _present(value: str) -> FieldValue:
    return FieldValue(raw_value=value, status="present", source_page=1)


def _missing() -> FieldValue:
    return FieldValue(raw_value=None, status="missing")


def _clean_fields(**overrides: FieldValue) -> ExtractedFields:
    base = {
        "customer_name": _present("Aarav Mehta"),
        "address": _present("42 Example Avenue, Vijayawada"),
        "document_type": _present("Proof of Address"),
        "document_date": _present("2026-09-01"),
        "issuer_name": _present("Example Bank"),
        "document_number": _present("DOC-123"),
        "postal_code": _present("520001"),
    }
    base.update(overrides)
    return ExtractedFields(**base)


def test_name_case_and_whitespace_normalize_consistently() -> None:
    assert normalize_name("  AARAV   Mehta ") == normalize_name("aarav mehta")
    assert normalize_name("Aarav, Mehta!") == "aarav mehta"


def test_material_name_differences_remain_different() -> None:
    assert normalize_name("Aarav Mehta") != normalize_name("Aarav Sharma")


def test_address_case_and_spacing_normalize_consistently() -> None:
    assert normalize_address("42  Example Avenue,Vijayawada") == normalize_address(
        "42 example avenue, vijayawada"
    )


def test_material_address_differences_remain_different() -> None:
    assert normalize_address("42 Example Avenue, Vijayawada") != normalize_address(
        "99 Synthetic Street, Vijayawada"
    )


def test_postal_code_normalizes_case_and_spacing() -> None:
    assert normalize_postal_code(" 520 001 ") == "520001"
    assert normalize_postal_code("ab 12cd") == "AB12CD"


def test_document_date_reformats_recognized_dates() -> None:
    assert normalize_document_date("01/09/2026") == "2026-09-01"
    assert normalize_document_date("2026-09-01") == "2026-09-01"


def test_impossible_date_passes_through_for_validators() -> None:
    assert normalize_document_date("2026-02-30") == "2026-02-30"


def test_missing_fields_keep_none_normalized() -> None:
    assert normalize_value("customer_name", None, status="missing") is None
    assert normalize_value("address", None, status="uncertain") is None


def test_unknown_field_is_explicit() -> None:
    with pytest.raises(NormalizationError) as exc_info:
        normalize_value("passport_number", "X", status="present")
    assert exc_info.value.code == "UNKNOWN_FIELD"


def test_full_record_preserves_status_and_evidence_refs() -> None:
    fields = _clean_fields(address=_missing())
    result = normalize_fields(fields)

    assert result.customer_name.normalized_value == "aarav mehta"
    assert result.customer_name.raw_value == "Aarav Mehta"
    assert result.customer_name.status == "present"
    assert result.address.status == "missing"
    assert result.address.normalized_value is None
    assert result.postal_code.normalized_value == "520001"
    assert result.document_date.normalized_value == "2026-09-01"


def test_normalize_fields_rejects_wrong_input() -> None:
    with pytest.raises(NormalizationError) as exc_info:
        normalize_fields({"customer_name": "x"})  # type: ignore[arg-type]
    assert exc_info.value.code == "INVALID_INPUT_TYPE"


# ---------------------------------------------------------------------------
# VER-02: Field validators (DoD: required cases pass with explicit finding
# codes; missing date and invalid date return expected findings)
# ---------------------------------------------------------------------------

from app.core.contracts import NormalizedFieldValue  # noqa: E402
from app.verification.validate import (  # noqa: E402
    ValidationError as _ValidationError,
)
from app.verification.validate import is_valid as _is_valid
from app.verification.validate import validate_fields as _validate_fields


def _nfields(**overrides) -> ExtractedFields:
    from app.verification.normalize import normalize_fields as _nf

    return _nf(_clean_fields(**overrides))


def test_clean_normalized_fields_have_no_findings() -> None:
    fields = _nfields()

    assert _validate_fields(fields) == []
    assert _is_valid(fields) is True


def test_missing_required_address_returns_expected_finding() -> None:
    fields = _nfields(address=FieldValue(raw_value=None, status="missing"))

    findings = _validate_fields(fields)

    codes = {(f.field_name, f.code, f.severity) for f in findings}
    assert ("address", "MISSING_ADDRESS", "error") in codes
    assert _is_valid(fields) is False


def test_invalid_document_date_returns_expected_finding() -> None:
    fields = _nfields(
        document_date=FieldValue(raw_value="2026-02-30", status="present", source_page=1)
    )
    normalized = fields.model_copy(
        update={
            "document_date": NormalizedFieldValue(
                raw_value="2026-02-30",
                status="present",
                source_page=1,
                normalized_value="2026-02-30",
            )
        }
    )

    findings = _validate_fields(normalized)

    assert [(x.field_name, x.code) for x in findings] == [
        ("document_date", "INVALID_DOCUMENT_DATE")
    ]
    assert _is_valid(normalized) is False


def test_uncertain_postal_code_returns_warning_finding() -> None:
    fields = _nfields(
        postal_code=FieldValue(raw_value=None, status="uncertain", source_page=1)
    )

    findings = _validate_fields(fields)

    assert [(x.field_name, x.code, x.severity) for x in findings] == [
        ("postal_code", "UNCERTAIN_POSTAL_CODE", "warning")
    ]
    assert _is_valid(fields) is True


def test_unreadable_postal_code_is_invalid() -> None:
    raw = _clean_fields(postal_code=FieldValue(raw_value="???", status="present"))
    from app.verification.normalize import normalize_fields as _nf2

    normalized = _nf2(raw)

    findings = _validate_fields(normalized)

    assert [(x.field_name, x.code) for x in findings] == [
        ("postal_code", "INVALID_POSTAL_CODE")
    ]
    assert _is_valid(normalized) is False


def test_validate_fields_rejects_wrong_input() -> None:
    with pytest.raises(_ValidationError) as exc_info:
        _validate_fields("not-fields")  # type: ignore[arg-type]
    assert exc_info.value.code == "INVALID_INPUT_TYPE"


# ---------------------------------------------------------------------------
# VER-03: Customer reference lookup (DoD: positive and negative tests;
# known ID returns the record, unknown ID returns controlled not_found)
# ---------------------------------------------------------------------------

from pathlib import Path as _Path  # noqa: E402

from app.db.init_db import initialize_database as _init_db  # noqa: E402
from app.db.repository import get_customer_by_id as _get_customer  # noqa: E402
from app.verification.reference import (  # noqa: E402
    ReferenceError as _ReferenceError,
)
from app.verification.reference import lookup_reference as _lookup
from scripts.seed_db import seed_customers as _seed  # noqa: E402


def _seeded_db(tmp_path: _Path) -> _Path:
    db_path = tmp_path / "ref.db"
    _init_db(db_path)
    assert _seed(db_path) == 5
    return db_path


def test_known_id_returns_correct_record(tmp_path: _Path) -> None:
    db_path = _seeded_db(tmp_path)

    result = _lookup(db_path, "CUST-0001")

    assert result.found is True
    assert result.code == "found"
    assert result.customer == {
        "customer_id": "CUST-0001",
        "customer_name": "Aarav Mehta",
        "address": "42 Example Avenue, Vijayawada",
        "postal_code": "520001",
    }


def test_unknown_id_returns_controlled_not_found(tmp_path: _Path) -> None:
    db_path = _seeded_db(tmp_path)

    result = _lookup(db_path, "CUST-9999")

    assert result.found is False
    assert result.code == "not_found"
    assert result.customer is None


def test_repository_returns_none_for_unknown_id(tmp_path: _Path) -> None:
    db_path = _seeded_db(tmp_path)

    assert _get_customer(db_path, "CUST-9999") is None


def test_empty_id_is_explicit_failure(tmp_path: _Path) -> None:
    db_path = _seeded_db(tmp_path)

    with pytest.raises(_ReferenceError) as exc_info:
        _lookup(db_path, "   ")
    assert exc_info.value.code == "EMPTY_CUSTOMER_ID"


# ---------------------------------------------------------------------------
# VER-04: Field-by-field comparison (DoD: deterministic output with observed
# and reference values; clean and mismatch DATA-04 cases give expected
# field outcomes)
# ---------------------------------------------------------------------------

from app.verification.compare import (  # noqa: E402
    ComparisonError as _ComparisonError,
)
from app.verification.compare import compare_fields as _compare
from app.verification.compare import mismatch_fields as _mismatches


def _doc(text: str):
    from app.document.field_parser import parse_fields as _parse
    from app.verification.normalize import normalize_fields as _nf

    return _nf(_parse(text).fields)


_REF = {
    "customer_id": "CUST-0001",
    "customer_name": "Aarav Mehta",
    "address": "42 Example Avenue, Vijayawada",
    "postal_code": "520001",
}


def test_clean_case_matches_all_fields() -> None:
    doc = _doc("Customer Name\nAarav Mehta\nAddress\n42 Example Avenue, Vijayawada\nPostal Code\n520001")

    comparisons = _compare(doc, _REF)

    assert [(c.field_name, c.status) for c in comparisons] == [
        ("customer_name", "match"),
        ("address", "match"),
        ("postal_code", "match"),
    ]
    assert comparisons[0].observed_value == "aarav mehta"
    assert comparisons[0].reference_value == "aarav mehta"
    assert _mismatches(comparisons) == []


def test_name_mismatch_case_flags_only_name() -> None:
    doc = _doc("Customer Name\nAarav Sharma\nAddress\n42 Example Avenue, Vijayawada\nPostal Code\n520001")

    comparisons = _compare(doc, _REF)

    assert [(c.field_name, c.status) for c in comparisons] == [
        ("customer_name", "mismatch"),
        ("address", "match"),
        ("postal_code", "match"),
    ]
    assert comparisons[0].observed_value == "aarav sharma"
    assert comparisons[0].reference_value == "aarav mehta"
    assert _mismatches(comparisons) == ["customer_name"]


def test_address_mismatch_case_flags_only_address() -> None:
    doc = _doc("Customer Name\nAarav Mehta\nAddress\n99 Synthetic Street, Vijayawada\nPostal Code\n520001")

    assert [(c.field_name, c.status) for c in _compare(doc, _REF)] == [
        ("customer_name", "match"),
        ("address", "mismatch"),
        ("postal_code", "match"),
    ]


def test_missing_address_compares_as_missing() -> None:
    doc = _doc("Customer Name\nAarav Mehta\nAddress\n\nPostal Code\n520001")

    comparisons = _compare(doc, _REF)

    assert comparisons[1].status == "missing"
    assert comparisons[1].reference_value == "42 example avenue, vijayawada"


def test_unknown_customer_is_unavailable() -> None:
    doc = _doc("Customer Name\nSynthetic Unknown Customer")

    comparisons = _compare(doc, None)

    assert {c.status for c in comparisons} == {"unavailable"}
    assert all(c.reference_value is None for c in comparisons)


def test_comparison_is_deterministic() -> None:
    doc = _doc("Customer Name\nAarav Mehta\nPostal Code\n520001")

    first = [(c.field_name, c.status, c.observed_value, c.reference_value) for c in _compare(doc, _REF)]
    second = [(c.field_name, c.status, c.observed_value, c.reference_value) for c in _compare(doc, _REF)]

    assert first == second


def test_compare_rejects_wrong_input() -> None:
    with pytest.raises(_ComparisonError) as exc_info:
        _compare("not-fields", _REF)  # type: ignore[arg-type]
    assert exc_info.value.code == "INVALID_INPUT_TYPE"
