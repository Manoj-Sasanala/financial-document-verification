"""DB-03: extracted_fields persistence.

Round-trip storage for DOC-05/DOC-06 field output: raw values, normalized
values and evidence metadata stay distinct rows per (case_id, field_name).

The repository works against databases created by
:func:`app.db.init_db.initialize_database` (schema upgrades are idempotent,
so existing databases gain the new table on next initialization).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.core.contracts import NormalizedFields


class RepositoryError(ValueError):
    """Controlled repository failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def save_extracted_fields(
    db_path: str | Path,
    case_id: str,
    fields: NormalizedFields,
) -> int:
    """Upsert all seven frozen fields for a case. Returns rows written."""
    if not case_id or not case_id.strip():
        raise RepositoryError("EMPTY_CASE_ID", "case_id must be a non-empty string.")
    if not isinstance(fields, NormalizedFields):
        raise RepositoryError("INVALID_INPUT_TYPE", "fields must be NormalizedFields.")

    rows = [
        (
            case_id,
            name,
            getattr(fields, name).raw_value,
            getattr(fields, name).normalized_value,
            getattr(fields, name).status,
            getattr(fields, name).source_page,
            getattr(fields, name).source_reference,
        )
        for name in NormalizedFields.model_fields
    ]
    try:
        with sqlite3.connect(db_path) as connection:
            connection.executemany(
                """
                INSERT INTO extracted_fields (
                    case_id,
                    field_name,
                    raw_value,
                    normalized_value,
                    status,
                    source_page,
                    source_reference
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (case_id, field_name)
                DO UPDATE SET
                    raw_value = excluded.raw_value,
                    normalized_value = excluded.normalized_value,
                    status = excluded.status,
                    source_page = excluded.source_page,
                    source_reference = excluded.source_reference
                """,
                rows,
            )
    except sqlite3.IntegrityError as exc:
        raise RepositoryError(
            "INTEGRITY_VIOLATION", f"extracted_fields write rejected: {exc}"
        ) from exc
    return len(rows)


def load_extracted_fields(db_path: str | Path, case_id: str) -> dict[str, dict[str, Any]]:
    """Load all stored fields for a case, keyed by field name."""
    if not case_id or not case_id.strip():
        raise RepositoryError("EMPTY_CASE_ID", "case_id must be a non-empty string.")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                field_name,
                raw_value,
                normalized_value,
                status,
                source_page,
                source_reference
            FROM extracted_fields
            WHERE case_id = ?
            ORDER BY field_name
            """,
            (case_id,),
        ).fetchall()
    if not rows:
        raise RepositoryError("FIELDS_NOT_FOUND", f"No extracted fields for {case_id}.")
    return {row["field_name"]: dict(row) for row in rows}


CUSTOMER_COLUMNS = ("customer_id", "customer_name", "address", "postal_code")

FINDING_KINDS = ("finding", "comparison", "indicator")


def get_customer_by_id(
    db_path: str | Path, customer_id: str
) -> dict[str, Any] | None:
    """Return the customer row for an ID, or None when not found.

    Controlled ``None`` (not an exception) is the not_found signal consumed
    by VER-03 reference lookup.
    """
    if not isinstance(customer_id, str) or not customer_id.strip():
        raise RepositoryError("EMPTY_CUSTOMER_ID", "customer_id must be non-empty.")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """
                SELECT customer_id, customer_name, address, postal_code
                FROM customers
                WHERE customer_id = ?
                """,
                (customer_id.strip(),),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            raise RepositoryError(
                "CUSTOMERS_UNAVAILABLE", f"customers table unavailable: {exc}"
            ) from exc
    return dict(row) if row is not None else None


def save_findings(
    db_path: str | Path,
    case_id: str,
    *,
    findings: list | None = None,
    comparisons: list | None = None,
    indicators: list | None = None,
) -> int:
    """Persist validation findings, comparisons and risk indicators.

    Every triggered indicator is stored with rule ID/version, severity,
    category, reason and observed/reference values for reviewer UI and
    case retrieval consumers.
    """
    from app.core.contracts import FieldComparison, Finding, RiskIndicator

    if not case_id or not str(case_id).strip():
        raise RepositoryError("EMPTY_CASE_ID", "case_id must be a non-empty string.")

    rows: list[tuple] = []
    for finding in findings or []:
        if not isinstance(finding, Finding):
            raise RepositoryError("INVALID_FINDING", "All findings must be Finding.")
        rows.append(
            (case_id, "finding", finding.field_name, finding.code, finding.reason,
             finding.severity, None, None, None, None, None)
        )
    for comparison in comparisons or []:
        if not isinstance(comparison, FieldComparison):
            raise RepositoryError("INVALID_COMPARISON", "All comparisons must be FieldComparison.")
        rows.append(
            (case_id, "comparison", comparison.field_name, comparison.status, None,
             None, None, comparison.observed_value, comparison.reference_value, None, None)
        )
    for indicator in indicators or []:
        if not isinstance(indicator, RiskIndicator):
            raise RepositoryError("INVALID_INDICATOR", "All indicators must be RiskIndicator.")
        rows.append(
            (case_id, "indicator", indicator.indicator_code, indicator.indicator_code,
             indicator.reason, indicator.severity, indicator.category, None, None,
             indicator.rule_id, indicator.rule_version)
        )
    if not rows:
        raise RepositoryError("EMPTY_FINDINGS", "Nothing to persist: all inputs empty.")

    try:
        with sqlite3.connect(db_path) as connection:
            connection.executemany(
                """
                INSERT INTO findings (
                    case_id, kind, ref, code, reason, severity, category,
                    observed_value, reference_value, rule_id, rule_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (case_id, kind, ref, code)
                DO UPDATE SET
                    reason = excluded.reason,
                    severity = excluded.severity,
                    category = excluded.category,
                    observed_value = excluded.observed_value,
                    reference_value = excluded.reference_value,
                    rule_id = excluded.rule_id,
                    rule_version = excluded.rule_version
                """,
                rows,
            )
    except sqlite3.IntegrityError as exc:
        raise RepositoryError(
            "INTEGRITY_VIOLATION", f"findings write rejected: {exc}"
        ) from exc
    return len(rows)


def load_findings(db_path: str | Path, case_id: str) -> list[dict[str, Any]]:
    """Load all stored finding rows for a case, ordered by kind and ref."""
    if not case_id or not str(case_id).strip():
        raise RepositoryError("EMPTY_CASE_ID", "case_id must be a non-empty string.")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                kind, ref, code, reason, severity, category,
                observed_value, reference_value, rule_id, rule_version
            FROM findings
            WHERE case_id = ?
            ORDER BY kind, ref, code
            """,
            (case_id,),
        ).fetchall()
    if not rows:
        raise RepositoryError("FINDINGS_NOT_FOUND", f"No findings for {case_id}.")
    return [dict(row) for row in rows]


def save_ai_result(
    db_path: str | Path,
    case_id: str,
    *,
    ml_classification: str,
    model_version: str,
    retrieval_status: str,
    evidence_refs: list[dict[str, str]] | None = None,
    explanation_status: str,
    explanation_text: str | None = None,
) -> str:
    """Upsert one AI result row per case; returns the case_id."""
    import json as _json

    from app.core.contracts import ExplanationResult, MLResult, RetrievalResult

    if not case_id or not str(case_id).strip():
        raise RepositoryError("EMPTY_CASE_ID", "case_id must be a non-empty string.")
    try:
        MLResult(classification=ml_classification, model_version=model_version)  # type: ignore[arg-type]
    except Exception as exc:
        raise RepositoryError("INVALID_ML_RESULT", f"Invalid ML result: {exc}") from exc
    try:
        RetrievalResult(status=retrieval_status, evidence=[])  # type: ignore[arg-type]
    except Exception as exc:
        raise RepositoryError("INVALID_RETRIEVAL", f"Invalid retrieval status: {exc}") from exc
    try:
        ExplanationResult(
            status=explanation_status, explanation=explanation_text, evidence_refs=[]  # type: ignore[arg-type]
        )
    except Exception as exc:
        raise RepositoryError("INVALID_EXPLANATION", f"Invalid explanation status: {exc}") from exc
    if not model_version or not str(model_version).strip():
        raise RepositoryError("VERSION_MISSING", "model_version must be non-empty.")

    refs = evidence_refs or []
    for ref in refs:
        if not {"source_id", "version", "chunk_id"} <= set(ref):
            raise RepositoryError("INVALID_EVIDENCE_REF", f"Bad evidence ref: {ref!r}.")

    try:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO ai_results (
                    case_id,
                    ml_classification,
                    model_version,
                    retrieval_status,
                    evidence_refs_json,
                    explanation_status,
                    explanation_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (case_id)
                DO UPDATE SET
                    ml_classification = excluded.ml_classification,
                    model_version = excluded.model_version,
                    retrieval_status = excluded.retrieval_status,
                    evidence_refs_json = excluded.evidence_refs_json,
                    explanation_status = excluded.explanation_status,
                    explanation_text = excluded.explanation_text
                """,
                (
                    case_id,
                    ml_classification,
                    model_version,
                    retrieval_status,
                    _json.dumps(refs),
                    explanation_status,
                    explanation_text,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise RepositoryError(
            "INTEGRITY_VIOLATION", f"ai_results write rejected: {exc}"
        ) from exc
    return case_id


def load_ai_result(db_path: str | Path, case_id: str) -> dict[str, Any]:
    """Load the AI result row for a case, with evidence refs decoded."""
    import json as _json

    if not case_id or not str(case_id).strip():
        raise RepositoryError("EMPTY_CASE_ID", "case_id must be a non-empty string.")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                case_id,
                ml_classification,
                model_version,
                retrieval_status,
                evidence_refs_json,
                explanation_status,
                explanation_text
            FROM ai_results
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()
    if row is None:
        raise RepositoryError("AI_RESULT_NOT_FOUND", f"No AI result for {case_id}.")
    record = dict(row)
    try:
        record["evidence_refs"] = _json.loads(record.pop("evidence_refs_json"))
    except Exception as exc:
        raise RepositoryError("INVALID_EVIDENCE_REF", f"Stored refs unreadable: {exc}") from exc
    return record


CASE_STATUSES = ("processing", "completed", "completed_with_warnings", "failed")
REVIEW_DECISIONS = ("approve", "reject", "request_information")


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def create_case(
    db_path: str | Path,
    case_id: str,
    customer_id: str,
    original_filename: str,
    content_type: str,
    *,
    status: str = "processing",
) -> str:
    """Create a case row; customer must already exist."""
    if not case_id or not str(case_id).strip():
        raise RepositoryError("EMPTY_CASE_ID", "case_id must be a non-empty string.")
    if status not in CASE_STATUSES:
        raise RepositoryError("INVALID_STATUS", f"Invalid case status: {status!r}.")
    if get_customer_by_id(db_path, customer_id) is None:
        raise RepositoryError("CUSTOMER_NOT_FOUND", f"Unknown customer: {customer_id}.")
    stamp = _now_iso()
    try:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO cases (
                    case_id, customer_id, original_filename, content_type,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (case_id, customer_id, original_filename, content_type, status, stamp, stamp),
            )
    except sqlite3.IntegrityError as exc:
        raise RepositoryError("CASE_EXISTS", f"Case write rejected: {exc}") from exc
    return case_id


def update_case_status(db_path: str | Path, case_id: str, status: str) -> None:
    """Move a case to a new lifecycle status."""
    if status not in CASE_STATUSES:
        raise RepositoryError("INVALID_STATUS", f"Invalid case status: {status!r}.")
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE cases SET status = ?, updated_at = ? WHERE case_id = ?",
            (status, _now_iso(), case_id),
        )
    if cursor.rowcount == 0:
        raise RepositoryError("CASE_NOT_FOUND", f"Unknown case: {case_id}.")


def save_review(
    db_path: str | Path,
    case_id: str,
    decision: str,
    comment: str | None = None,
) -> None:
    """Record the human reviewer decision for a case."""
    if decision not in REVIEW_DECISIONS:
        raise RepositoryError("INVALID_DECISION", f"Invalid review decision: {decision!r}.")
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE cases
            SET review_decision = ?, review_comment = ?, reviewed_at = ?
            WHERE case_id = ?
            """,
            (decision, comment, _now_iso(), case_id),
        )
    if cursor.rowcount == 0:
        raise RepositoryError("CASE_NOT_FOUND", f"Unknown case: {case_id}.")


def get_case(db_path: str | Path, case_id: str) -> dict[str, Any]:
    """Reconstruct a complete case: row, fields, findings and AI result."""
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
    if row is None:
        raise RepositoryError("CASE_NOT_FOUND", f"Unknown case: {case_id}.")
    case = dict(row)
    try:
        case["extracted_fields"] = load_extracted_fields(db_path, case_id)
    except RepositoryError:
        case["extracted_fields"] = {}
    try:
        case["findings"] = load_findings(db_path, case_id)
    except RepositoryError:
        case["findings"] = []
    try:
        case["ai_result"] = load_ai_result(db_path, case_id)
    except RepositoryError:
        case["ai_result"] = None
    return case


__all__ = [
    "RepositoryError",
    "create_case",
    "get_case",
    "get_customer_by_id",
    "load_ai_result",
    "load_extracted_fields",
    "load_findings",
    "save_ai_result",
    "save_extracted_fields",
    "save_findings",
    "save_review",
    "update_case_status",
    "CASE_STATUSES",
    "CUSTOMER_COLUMNS",
    "FINDING_KINDS",
    "REVIEW_DECISIONS",
]
