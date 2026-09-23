"""VER-01: Field normalization.

Standardizes document values before comparison (DOC-04 structured fields in,
frozen ``NormalizedFields`` out).

Deterministic boundaries (frozen for VER-01):
  * Names: Unicode casefold, punctuation removed, inner whitespace collapsed.
  * Addresses: casefold, punctuation (except commas) removed, whitespace and
    comma spacing collapsed.
  * Postal codes: whitespace removed, uppercased.
  * Document dates: stripped; recognized calendar dates reformatted to
    ``YYYY-MM-DD``; unrecognized or impossible dates pass through unchanged
    (validation, not normalization, rejects them downstream).
  * Document type / issuer / number: casefold + whitespace collapse.
  * ``missing`` / ``uncertain`` fields keep ``normalized_value=None`` with
    status and evidence refs preserved — normalization never fills gaps.

Explicit failure states use :class:`NormalizationError` with a stable ``code``.

Consumer: validators and reference matcher.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from app.core.contracts import ExtractedFields, NormalizedFields, NormalizedFieldValue

_WHITESPACE_RUN = re.compile(r"\s+")
_NAME_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_ADDRESS_PUNCT = re.compile(r"[^\w\s,]", re.UNICODE)
_COMMA_RUN = re.compile(r"\s*,\s*")

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%d %B %Y",
)


class NormalizationError(ValueError):
    """Controlled normalization failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _collapse(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", text).strip()


def normalize_name(value: str) -> str:
    """Casefold, drop punctuation, collapse whitespace."""
    cleaned = unicodedata.normalize("NFKC", value)
    cleaned = _NAME_PUNCT.sub("", cleaned)
    return _collapse(cleaned).casefold()


def normalize_address(value: str) -> str:
    """Casefold, keep commas, collapse whitespace/comma spacing."""
    cleaned = unicodedata.normalize("NFKC", value)
    cleaned = _ADDRESS_PUNCT.sub("", cleaned)
    cleaned = _COMMA_RUN.sub(", ", cleaned)
    return _collapse(cleaned).casefold()


def normalize_postal_code(value: str) -> str:
    """Remove all whitespace, uppercase (leading zeroes preserved)."""
    return _WHITESPACE_RUN.sub("", value).strip().upper()


def normalize_document_date(value: str) -> str:
    """Reformat recognized calendar dates to YYYY-MM-DD; pass others through."""
    stripped = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    iso = stripped.replace("/", "-")
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d")
    except ValueError:
        return stripped


def normalize_generic(value: str) -> str:
    """Casefold + whitespace collapse for type/issuer/number fields."""
    return _collapse(unicodedata.normalize("NFKC", value)).casefold()


NORMALIZERS = {
    "customer_name": normalize_name,
    "address": normalize_address,
    "document_type": normalize_generic,
    "document_date": normalize_document_date,
    "issuer_name": normalize_generic,
    "document_number": normalize_generic,
    "postal_code": normalize_postal_code,
}


def normalize_value(field_name: str, value: str | None, *, status: str) -> str | None:
    """Normalize one raw value; None stays None for missing/uncertain."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise NormalizationError("INVALID_INPUT_TYPE", f"{field_name} value must be str.")
    if status in ("missing", "uncertain"):
        return None
    normalizer = NORMALIZERS.get(field_name)
    if normalizer is None:
        raise NormalizationError("UNKNOWN_FIELD", f"Unknown field: {field_name}.")
    return normalizer(value)


def normalize_fields(fields: ExtractedFields) -> NormalizedFields:
    """Normalize a full frozen ``ExtractedFields`` record."""
    if not isinstance(fields, ExtractedFields):
        raise NormalizationError("INVALID_INPUT_TYPE", "fields must be ExtractedFields.")
    normalized: dict[str, NormalizedFieldValue] = {}
    for name in ExtractedFields.model_fields:
        current = getattr(fields, name)
        normalized[name] = NormalizedFieldValue(
            raw_value=current.raw_value,
            status=current.status,  # type: ignore[arg-type]
            source_page=current.source_page,
            source_reference=current.source_reference,
            normalized_value=normalize_value(name, current.raw_value, status=current.status),
        )
    return NormalizedFields(**normalized)


__all__ = [
    "NormalizationError",
    "normalize_address",
    "normalize_document_date",
    "normalize_fields",
    "normalize_generic",
    "normalize_name",
    "normalize_postal_code",
    "normalize_value",
    "NORMALIZERS",
]
