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
