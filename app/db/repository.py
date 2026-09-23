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


__all__ = [
    "RepositoryError",
    "load_extracted_fields",
    "save_extracted_fields",
]
