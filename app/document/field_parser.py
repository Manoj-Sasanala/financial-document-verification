"""DOC-04: Fixed field parser.

Converts DOC-02/DOC-03 extracted text into the frozen ``ExtractedFields``
schema (``app/core/contracts.py`` — never edited here).

Parsing boundary (deterministic):
  * Label-anchored extraction: a value is only assigned when its template
    label (e.g. ``Customer Name``) is found in the text, either as
    ``Label`` + newline + ``value`` or ``Label: value`` (case-insensitive).
  * Fields whose label is absent are returned with ``status="missing"`` and
    ``raw_value=None`` — the parser never invents missing fields.
  * A present label with an empty value yields ``status="uncertain"``.
  * ``customer_id`` is a document reference key, not part of the frozen
    seven-field ``ExtractedFields`` contract; it is returned separately in
    :class:`ParsedDocument` for downstream reference lookup without
    polluting the frozen schema.

Explicit failure states use :class:`FieldParserError` with a stable ``code``.
Evidence (source page / source reference per field) is preserved for the
normalizer/validator consumer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.contracts import ExtractedFields, FieldValue

# Template labels (DATA-03) mapped to frozen ExtractedFields names.
LABEL_TO_FIELD: dict[str, str] = {
    "customer name": "customer_name",
    "address": "address",
    "document type": "document_type",
    "document date": "document_date",
    "issuer name": "issuer_name",
    "issuer": "issuer_name",
    "document number": "document_number",
    "postal code": "postal_code",
}

CUSTOMER_ID_LABELS = ("customer id", "customer no", "customer number")

CUSTOMER_ID_PATTERN = re.compile(r"\bCUST-\d{4,}\b")
POSTAL_CODE_PATTERN = re.compile(r"\b\d{5,6}\b")


class FieldParserError(ValueError):
    """Controlled parser failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass(frozen=True)
class ParsedDocument:
    """Parser output: frozen fields plus the document reference key."""

    fields: ExtractedFields
    customer_id: str | None = None
    provenance: dict[str, str | int | None] = field(default_factory=dict)


def _find_label_value(lines: list[str], label: str) -> str | None:
    """Return the value for a label, None when the label is absent.

    Supports ``Label`` on its own line followed by the value on the next
    non-empty line, and inline ``Label: value`` / ``Label - value`` forms.
    """
    lowered = label.lower()
    known_labels = set(LABEL_TO_FIELD) | set(CUSTOMER_ID_LABELS)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if low == lowered:
            # Only the immediately following line belongs to this label. A
            # blank line or another label means the value is empty.
            if index + 1 >= len(lines):
                return ""
            following = lines[index + 1].strip()
            if not following or following.lower() in known_labels:
                return ""
            return following
        for sep in (":", "-", "\u2013", "\u2014"):
            if low.startswith(lowered + sep) or low.startswith(lowered + " " + sep):
                return stripped.split(sep, 1)[1].strip()
    return None


def _present(value: str | None, *, source_page: int, ref: str) -> FieldValue:
    if value is None:
        return FieldValue(raw_value=None, status="missing")
    if not value.strip():
        return FieldValue(raw_value=None, status="uncertain", source_page=source_page)
    return FieldValue(
        raw_value=value.strip(),
        status="present",
        source_page=source_page,
        source_reference=ref,
    )


def parse_fields(
    text: str,
    *,
    source_page: int = 1,
    source_name: str = "page-1",
) -> ParsedDocument:
    """Parse extracted text into the frozen ``ExtractedFields`` schema.

    Args:
        text: Native (DOC-02) or OCR (DOC-03) extracted text.
        source_page: 1-based page number for evidence refs.
        source_name: Provenance label for the text origin.

    Raises:
        :class:`FieldParserError`: ``EMPTY_TEXT`` for blank input,
            ``INVALID_INPUT_TYPE`` for non-string input.
    """
    if not isinstance(text, str):
        raise FieldParserError("INVALID_INPUT_TYPE", "text must be of type str.")
    if not text.strip():
        raise FieldParserError("EMPTY_TEXT", "No extracted text to parse.")

    lines = text.splitlines()
    values: dict[str, FieldValue] = {}

    for label, field_name in LABEL_TO_FIELD.items():
        raw = _find_label_value(lines, label)
        ref = f"{source_name}#{label.replace(' ', '-')}"
        value = _present(raw, source_page=source_page, ref=ref)

        # Postal code must look like a code; otherwise mark uncertain rather
        # than storing a non-code string as fact.
        if (
            field_name == "postal_code"
            and value.status == "present"
            and value.raw_value is not None
            and not POSTAL_CODE_PATTERN.search(value.raw_value)
        ):
            value = FieldValue(raw_value=None, status="uncertain", source_page=source_page)
        values[field_name] = value

    # customer_id is a reference key outside the frozen schema: extract it
    # when its label or CUST-NNNN pattern is present, else leave None.
    customer_id: str | None = None
    for label in CUSTOMER_ID_LABELS:
        raw = _find_label_value(lines, label)
        if raw:
            match = CUSTOMER_ID_PATTERN.search(raw)
            customer_id = match.group(0) if match else None
            break
    if customer_id is None:
        match = CUSTOMER_ID_PATTERN.search(text)
        customer_id = match.group(0) if match else None

    fields = ExtractedFields(**values)
    provenance: dict[str, str | int | None] = {
        "parser": "fixed-label/1.0.0",
        "source_name": source_name,
        "source_page": source_page,
        "task_id": "DOC-04",
    }
    return ParsedDocument(fields=fields, customer_id=customer_id, provenance=provenance)


__all__ = [
    "FieldParserError",
    "ParsedDocument",
    "parse_fields",
    "LABEL_TO_FIELD",
]
