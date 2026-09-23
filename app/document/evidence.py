"""DOC-05: Missing/uncertain field evidence.

Represents extraction uncertainty explicitly for DOC-04 parser output and
DATA-05 negative-path cases.

Boundary (deterministic):
  * Every frozen field gets one :class:`FieldEvidence` record carrying its
    ``present`` / ``missing`` / ``uncertain`` status verbatim.
  * Missing and uncertain fields keep ``raw_value=None`` — they are never
    silently filled, defaulted, or inferred.
  * The bundle hash (SHA-256 over the canonical status map) lets downstream
    stages prove the evidence they received matches what parsing produced.

Explicit failure states use :class:`EvidenceError` with a stable ``code``.

Consumer: validation; UI; persistence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from app.core.contracts import ExtractedFields
from app.document.field_parser import ParsedDocument

EVIDENCE_STATUSES = ("present", "missing", "uncertain")


class EvidenceError(ValueError):
    """Controlled evidence failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass(frozen=True)
class FieldEvidence:
    """Evidence record for one frozen field."""

    field_name: str
    status: str
    raw_value: str | None
    source_page: int | None = None
    source_reference: str | None = None


@dataclass(frozen=True)
class EvidenceBundle:
    """Full per-document evidence with integrity hash and provenance."""

    fields: list[FieldEvidence]
    bundle_hash: str = ""
    provenance: dict[str, str | int | None] = field(default_factory=dict)

    def status_of(self, field_name: str) -> str:
        for record in self.fields:
            if record.field_name == field_name:
                return record.status
        raise EvidenceError("UNKNOWN_FIELD", f"Unknown field: {field_name}")


def build_evidence(
    parsed: ParsedDocument,
    *,
    doc_sha256: str | None = None,
    extraction_method: str | None = None,
) -> EvidenceBundle:
    """Build the evidence bundle for one parsed document."""
    if not isinstance(parsed, ParsedDocument):
        raise EvidenceError("INVALID_INPUT_TYPE", "parsed must be a ParsedDocument.")
    if not isinstance(parsed.fields, ExtractedFields):
        raise EvidenceError("INVALID_FIELDS", "parsed.fields must be ExtractedFields.")

    records: list[FieldEvidence] = []
    for name in ExtractedFields.model_fields:
        value = getattr(parsed.fields, name)
        if value.status not in EVIDENCE_STATUSES:
            raise EvidenceError(
                "INVALID_STATUS", f"Field {name} has unexpected status {value.status!r}."
            )
        if value.status in ("missing", "uncertain") and value.raw_value is not None:
            raise EvidenceError(
                "SILENT_FILL_DETECTED",
                f"Field {name} is {value.status} but carries a raw value.",
            )
        records.append(
            FieldEvidence(
                field_name=name,
                status=value.status,
                raw_value=value.raw_value,
                source_page=value.source_page,
                source_reference=value.source_reference,
            )
        )

    status_map = {r.field_name: r.status for r in records}
    bundle_hash = hashlib.sha256(
        json.dumps(status_map, sort_keys=True).encode("utf-8")
    ).hexdigest()
    provenance: dict[str, str | int | None] = {
        "task_id": "DOC-05",
        "evidence_builder": "field-evidence/1.0.0",
        **parsed.provenance,
    }
    if doc_sha256:
        provenance["doc_sha256"] = doc_sha256
    if extraction_method:
        provenance["extraction_method"] = extraction_method
    return EvidenceBundle(fields=records, bundle_hash=bundle_hash, provenance=provenance)


def assert_no_silent_fill(bundle: EvidenceBundle, parsed: ParsedDocument) -> None:
    """Prove the bundle matches parser output exactly (no fills, no drops)."""
    for record in bundle.fields:
        current = getattr(parsed.fields, record.field_name)
        if record.status != current.status or record.raw_value != current.raw_value:
            raise EvidenceError(
                "EVIDENCE_MISMATCH",
                f"Evidence for {record.field_name} diverges from parser output.",
            )


__all__ = [
    "EvidenceBundle",
    "EvidenceError",
    "FieldEvidence",
    "assert_no_silent_fill",
    "build_evidence",
    "EVIDENCE_STATUSES",
]
