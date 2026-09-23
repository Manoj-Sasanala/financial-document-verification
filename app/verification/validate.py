"""VER-02: Field validators.

Detects missing and invalid field values on VER-01 normalized fields,
emitting frozen ``Finding`` records (field_name / code / reason / severity).

Deterministic boundaries (frozen for VER-02):
  * Required proof-of-address fields: ``customer_name``, ``address``,
    ``postal_code``. When missing → ``MISSING_<FIELD>`` (severity ``error``).
  * Optional document fields (type/date/issuer/number): missing is legitimate
    and yields no finding; present-but-invalid yields a finding.
  * ``uncertain`` status on any field → ``UNCERTAIN_<FIELD>`` (``warning``).
  * ``document_date`` must be a real calendar date in ``YYYY-MM-DD`` form,
    else ``INVALID_DOCUMENT_DATE`` (``error``).
  * ``postal_code`` must match ``^[0-9A-Z]{3,12}$`` (spaces stripped by
    normalization), else ``INVALID_POSTAL_CODE`` (``error``).
  * Findings are returned in frozen field order for reproducibility.

Explicit failure states use :class:`ValidationError` with a stable ``code``.

Consumer: reference comparison; risk rules.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.core.contracts import Finding, NormalizedFields

REQUIRED_FIELDS = ("customer_name", "address", "postal_code")

FIELD_ORDER = (
    "customer_name",
    "address",
    "document_type",
    "document_date",
    "issuer_name",
    "document_number",
    "postal_code",
)

POSTAL_CODE_PATTERN = re.compile(r"^[0-9A-Z]{3,12}$")


class ValidationError(ValueError):
    """Controlled validation failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _missing_code(field_name: str) -> str:
    return f"MISSING_{field_name.upper()}"


def _uncertain_code(field_name: str) -> str:
    return f"UNCERTAIN_{field_name.upper()}"


def validate_fields(fields: NormalizedFields) -> list[Finding]:
    """Validate normalized fields; return findings in frozen field order."""
    if not isinstance(fields, NormalizedFields):
        raise ValidationError("INVALID_INPUT_TYPE", "fields must be NormalizedFields.")

    findings: list[Finding] = []
    for name in FIELD_ORDER:
        value = getattr(fields, name)
        status = value.status
        normalized = value.normalized_value

        if status == "missing":
            if name in REQUIRED_FIELDS:
                findings.append(
                    Finding(
                        field_name=name,
                        code=_missing_code(name),
                        reason=f"Required field '{name}' is missing from the document.",
                        severity="error",
                    )
                )
            continue

        if status == "uncertain":
            findings.append(
                Finding(
                    field_name=name,
                    code=_uncertain_code(name),
                    reason=f"Field '{name}' could not be determined with confidence.",
                    severity="warning",
                )
            )
            continue

        if name == "document_date" and normalized is not None:
            try:
                datetime.strptime(normalized, "%Y-%m-%d")
            except ValueError:
                findings.append(
                    Finding(
                        field_name=name,
                        code="INVALID_DOCUMENT_DATE",
                        reason=f"Document date '{value.raw_value}' is not a valid calendar date.",
                        severity="error",
                    )
                )
        elif name == "postal_code" and normalized is not None:
            if not POSTAL_CODE_PATTERN.match(normalized):
                findings.append(
                    Finding(
                        field_name=name,
                        code="INVALID_POSTAL_CODE",
                        reason=f"Postal code '{value.raw_value}' has an unexpected format.",
                        severity="error",
                    )
                )

    return findings


def is_valid(fields: NormalizedFields) -> bool:
    """True when validation yields no ``error``-severity findings."""
    return all(f.severity != "error" for f in validate_fields(fields))


__all__ = [
    "ValidationError",
    "is_valid",
    "validate_fields",
    "FIELD_ORDER",
    "REQUIRED_FIELDS",
]
