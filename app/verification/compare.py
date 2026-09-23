"""VER-04: Field-by-field comparison.

Compares VER-01 normalized document values against the normalized VER-03
reference record, emitting frozen ``FieldComparison`` records
(field_name / status / observed_value / reference_value).

Deterministic boundaries (frozen for VER-04):
  * Compared fields: ``customer_name``, ``address``, ``postal_code`` — the
    reference record carries only these plus ``customer_id``.
  * Document ``missing``/``uncertain`` → ``status="missing"`` with the
    observed value (or None) and the reference value present.
  * Unknown customer (reference None) → ``status="unavailable"`` for every
    compared field.
  * Equal normalized values → ``match``; anything else → ``mismatch``.
  * Output order is fixed: customer_name, address, postal_code.

Explicit failure states use :class:`ComparisonError` with a stable ``code``.

Consumer: risk rules; reviewer UI.
"""

from __future__ import annotations

from typing import Any

from app.core.contracts import FieldComparison, NormalizedFields
from app.verification.normalize import (
    normalize_address,
    normalize_name,
    normalize_postal_code,
)

COMPARED_FIELDS = ("customer_name", "address", "postal_code")

_REFERENCE_NORMALIZERS = {
    "customer_name": normalize_name,
    "address": normalize_address,
    "postal_code": normalize_postal_code,
}


class ComparisonError(ValueError):
    """Controlled comparison failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def normalize_reference(reference: dict[str, Any]) -> dict[str, str | None]:
    """Normalize the four-field reference record with VER-01 normalizers."""
    if not isinstance(reference, dict):
        raise ComparisonError("INVALID_REFERENCE", "reference must be a dict.")
    normalized: dict[str, str | None] = {}
    for name in COMPARED_FIELDS:
        raw = reference.get(name)
        if raw is None:
            normalized[name] = None
        elif not isinstance(raw, str):
            raise ComparisonError("INVALID_REFERENCE", f"reference {name} must be str.")
        else:
            normalized[name] = _REFERENCE_NORMALIZERS[name](raw)
    return normalized


def compare_fields(
    document: NormalizedFields, reference: dict[str, Any] | None
) -> list[FieldComparison]:
    """Compare one normalized document against a reference record (or None)."""
    if not isinstance(document, NormalizedFields):
        raise ComparisonError("INVALID_INPUT_TYPE", "document must be NormalizedFields.")
    if reference is not None and not isinstance(reference, dict):
        raise ComparisonError("INVALID_REFERENCE", "reference must be a dict or None.")

    if reference is None:
        return [
            FieldComparison(
                field_name=name, status="unavailable",
                observed_value=getattr(document, name).normalized_value,
                reference_value=None,
            )
            for name in COMPARED_FIELDS
        ]

    ref_norm = normalize_reference(reference)
    comparisons: list[FieldComparison] = []
    for name in COMPARED_FIELDS:
        doc_value = getattr(document, name)
        observed = doc_value.normalized_value
        expected = ref_norm[name]
        if doc_value.status in ("missing", "uncertain") or observed is None:
            status = "missing"
        elif expected is None:
            status = "unavailable"
        elif observed == expected:
            status = "match"
        else:
            status = "mismatch"
        comparisons.append(
            FieldComparison(
                field_name=name,
                status=status,  # type: ignore[arg-type]
                observed_value=observed,
                reference_value=expected,
            )
        )
    return comparisons


def mismatch_fields(comparisons: list[FieldComparison]) -> list[str]:
    """Names of fields with ``mismatch`` status, in comparison order."""
    return [c.field_name for c in comparisons if c.status == "mismatch"]


__all__ = [
    "ComparisonError",
    "compare_fields",
    "mismatch_fields",
    "normalize_reference",
    "COMPARED_FIELDS",
]
