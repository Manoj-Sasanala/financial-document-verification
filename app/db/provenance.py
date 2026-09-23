"""DB-07: Provenance/version persistence.

Makes every important output traceable: processing timestamp, rule
versions, model version, policy source versions and extraction source
references are stored per case and surfaced in retrieved case data.

The ``provenance`` table holds one row per case. ``get_case`` includes it
under the ``provenance`` key (None when never recorded).

Explicit failure states reuse :class:`RepositoryError` codes.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.contracts import Provenance
from app.db.repository import RepositoryError

TASK_ID = "DB-07"


def save_provenance(
    db_path: str | Path,
    case_id: str,
    provenance: Provenance | dict[str, Any],
) -> str:
    """Upsert the provenance row for a case; returns the case_id."""
    if not case_id or not str(case_id).strip():
        raise RepositoryError("EMPTY_CASE_ID", "case_id must be a non-empty string.")
    if isinstance(provenance, Provenance):
        record = provenance.model_dump()
    elif isinstance(provenance, dict):
        record = dict(provenance)
    else:
        raise RepositoryError("INVALID_PROVENANCE", "provenance must be Provenance or dict.")

    try:
        validated = Provenance(**{
            "processed_at": record["processed_at"],
            "rule_versions": record.get("rule_versions", []),
            "model_version": record.get("model_version"),
            "policy_source_versions": record.get("policy_source_versions", []),
            "extraction_source_refs": record.get("extraction_source_refs"),
        })
    except Exception as exc:
        raise RepositoryError("INVALID_PROVENANCE", f"Provenance invalid: {exc}") from exc

    processed = validated.processed_at
    processed_text = processed.isoformat() if hasattr(processed, "isoformat") else str(processed)
    try:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO provenance (
                    case_id,
                    processed_at,
                    rule_versions_json,
                    model_version,
                    policy_source_versions_json,
                    extraction_source_refs_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (case_id)
                DO UPDATE SET
                    processed_at = excluded.processed_at,
                    rule_versions_json = excluded.rule_versions_json,
                    model_version = excluded.model_version,
                    policy_source_versions_json = excluded.policy_source_versions_json,
                    extraction_source_refs_json = excluded.extraction_source_refs_json
                """,
                (
                    case_id,
                    processed_text,
                    json.dumps(validated.rule_versions),
                    validated.model_version,
                    json.dumps(validated.policy_source_versions),
                    json.dumps(validated.extraction_source_refs or []),
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise RepositoryError(
            "INTEGRITY_VIOLATION", f"provenance write rejected: {exc}"
        ) from exc
    return case_id


def load_provenance(db_path: str | Path, case_id: str) -> dict[str, Any]:
    """Load the provenance record for a case with JSON fields decoded."""
    if not case_id or not str(case_id).strip():
        raise RepositoryError("EMPTY_CASE_ID", "case_id must be a non-empty string.")
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT
                case_id,
                processed_at,
                rule_versions_json,
                model_version,
                policy_source_versions_json,
                extraction_source_refs_json
            FROM provenance
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()
    if row is None:
        raise RepositoryError("PROVENANCE_NOT_FOUND", f"No provenance for {case_id}.")
    record = dict(row)
    try:
        record["rule_versions"] = json.loads(record.pop("rule_versions_json"))
        record["policy_source_versions"] = json.loads(record.pop("policy_source_versions_json"))
        record["extraction_source_refs"] = json.loads(record.pop("extraction_source_refs_json"))
    except Exception as exc:
        raise RepositoryError("INVALID_PROVENANCE", f"Stored provenance unreadable: {exc}") from exc
    return record


__all__ = ["RepositoryError", "load_provenance", "save_provenance", "TASK_ID"]
