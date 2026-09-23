import json
import sqlite3
from pathlib import Path

import pytest

from app.core.contracts import NormalizedFieldValue, NormalizedFields
from app.db.init_db import initialize_database
from app.db.repository import (
    RepositoryError,
    load_extracted_fields,
    save_extracted_fields,
)
from scripts.seed_db import seed_customers


def test_database_initialization_creates_customers_table(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'customers'
            """
        ).fetchone()

    assert table == ("customers",)


def test_seeded_customer_can_be_retrieved_by_customer_id(tmp_path: Path):
    db_path = tmp_path / "test.db"

    count = seed_customers(db_path)

    assert count == 5

    with sqlite3.connect(db_path) as connection:
        customer = connection.execute(
            """
            SELECT customer_id, customer_name, address, postal_code
            FROM customers
            WHERE customer_id = ?
            """,
            ("CUST-0001",),
        ).fetchone()

    assert customer == (
        "CUST-0001",
        "Aarav Mehta",
        "42 Example Avenue, Vijayawada",
        "520001",
    )


def test_seed_is_idempotent_for_customer_ids(tmp_path: Path):
    db_path = tmp_path / "test.db"

    seed_customers(db_path)
    seed_customers(db_path)

    with sqlite3.connect(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM customers"
        ).fetchone()[0]

    assert count == 5


def test_seed_uses_expected_customer_dataset():
    customers_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "synthetic"
        / "customers.json"
    )

    customers = json.loads(customers_path.read_text(encoding="utf-8"))

    assert len(customers) == 5
    assert {customer["customer_id"] for customer in customers} == {
        "CUST-0001",
        "CUST-0002",
        "CUST-0003",
        "CUST-0004",
        "CUST-0005",
    }
def test_database_initialization_creates_cases_table(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'cases'
            """
        ).fetchone()

    assert table == ("cases",)


def test_case_insert_update_and_read(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id,
                customer_name,
                address,
                postal_code
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "CUST-DB02",
                "Test Customer",
                "1 Test Street, Vijayawada",
                "520001",
            ),
        )

        connection.execute(
            """
            INSERT INTO cases (
                case_id,
                customer_id,
                original_filename,
                content_type,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CASE-DB02-001",
                "CUST-DB02",
                "proof_of_address.pdf",
                "application/pdf",
                "processing",
                "2026-09-23T10:00:00+00:00",
                "2026-09-23T10:00:00+00:00",
            ),
        )

        connection.execute(
            """
            UPDATE cases
            SET
                status = ?,
                updated_at = ?,
                review_decision = ?,
                review_comment = ?,
                reviewed_at = ?
            WHERE case_id = ?
            """,
            (
                "completed",
                "2026-09-23T10:05:00+00:00",
                "approve",
                "Verified successfully.",
                "2026-09-23T10:06:00+00:00",
                "CASE-DB02-001",
            ),
        )

        case = connection.execute(
            """
            SELECT
                case_id,
                customer_id,
                original_filename,
                content_type,
                status,
                created_at,
                updated_at,
                review_decision,
                review_comment,
                reviewed_at
            FROM cases
            WHERE case_id = ?
            """,
            ("CASE-DB02-001",),
        ).fetchone()

    assert case == (
        "CASE-DB02-001",
        "CUST-DB02",
        "proof_of_address.pdf",
        "application/pdf",
        "completed",
        "2026-09-23T10:00:00+00:00",
        "2026-09-23T10:05:00+00:00",
        "approve",
        "Verified successfully.",
        "2026-09-23T10:06:00+00:00",
    )


def test_case_state_survives_database_restart(tmp_path: Path):
    db_path = tmp_path / "persistent.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id,
                customer_name,
                address,
                postal_code
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "CUST-RESTART",
                "Restart Customer",
                "2 Persistence Street, Vijayawada",
                "520002",
            ),
        )

        connection.execute(
            """
            INSERT INTO cases (
                case_id,
                customer_id,
                original_filename,
                content_type,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CASE-RESTART-001",
                "CUST-RESTART",
                "address.pdf",
                "application/pdf",
                "completed_with_warnings",
                "2026-09-23T11:00:00+00:00",
                "2026-09-23T11:02:00+00:00",
            ),
        )

    # Simulate application restart by opening a new SQLite connection.
    with sqlite3.connect(db_path) as connection:
        case = connection.execute(
            """
            SELECT case_id, customer_id, status
            FROM cases
            WHERE case_id = ?
            """,
            ("CASE-RESTART-001",),
        ).fetchone()

    assert case == (
        "CASE-RESTART-001",
        "CUST-RESTART",
        "completed_with_warnings",
    )


def test_case_rejects_invalid_status(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id,
                customer_name,
                address,
                postal_code
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "CUST-STATUS",
                "Status Customer",
                "3 Status Street, Vijayawada",
                "520003",
            ),
        )

        try:
            connection.execute(
                """
                INSERT INTO cases (
                    case_id,
                    customer_id,
                    original_filename,
                    content_type,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "CASE-STATUS-001",
                    "CUST-STATUS",
                    "document.pdf",
                    "application/pdf",
                    "invalid_status",
                    "2026-09-23T12:00:00+00:00",
                    "2026-09-23T12:00:00+00:00",
                ),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Invalid case status was accepted")


def test_case_rejects_invalid_review_decision(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id,
                customer_name,
                address,
                postal_code
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "CUST-REVIEW",
                "Review Customer",
                "4 Review Street, Vijayawada",
                "520004",
            ),
        )

        connection.execute(
            """
            INSERT INTO cases (
                case_id,
                customer_id,
                original_filename,
                content_type,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CASE-REVIEW-001",
                "CUST-REVIEW",
                "document.pdf",
                "application/pdf",
                "completed",
                "2026-09-23T13:00:00+00:00",
                "2026-09-23T13:00:00+00:00",
            ),
        )

        with connection:
            try:
                connection.execute(
                    """
                    UPDATE cases
                    SET review_decision = ?
                    WHERE case_id = ?
                    """,
                    (
                        "invalid_decision",
                        "CASE-REVIEW-001",
                    ),
                )
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError(
                    "Invalid review decision was accepted"
                )


# ---------------------------------------------------------------------------
# DB-03: extracted_fields table (DoD: round-trip persistence passes; raw and
# normalized values remain distinct)
# ---------------------------------------------------------------------------


def _seed_case(db_path: Path, case_id: str = "CASE-DB03-001"):
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO customers (
                customer_id,
                customer_name,
                address,
                postal_code
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "CUST-DB03",
                "DB03 Customer",
                "5 Evidence Street, Vijayawada",
                "520005",
            ),
        )
        connection.execute(
            """
            INSERT INTO cases (
                case_id,
                customer_id,
                original_filename,
                content_type,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                "CUST-DB03",
                "proof.pdf",
                "application/pdf",
                "processing",
                "2026-09-23T14:00:00+00:00",
                "2026-09-23T14:00:00+00:00",
            ),
        )


def _db03_fields() -> NormalizedFields:
    def _present(raw, normalized):
        return NormalizedFieldValue(
            raw_value=raw,
            status="present",
            source_page=1,
            source_reference="page-1#field",
            normalized_value=normalized,
        )

    def _absent():
        return NormalizedFieldValue(raw_value=None, status="missing")

    return NormalizedFields(
        customer_name=_present("  AARAV Mehta ", "aarav mehta"),
        address=_present("42 Example Avenue, Vijayawada", "42 example avenue, vijayawada"),
        document_type=_absent(),
        document_date=_absent(),
        issuer_name=_absent(),
        document_number=_absent(),
        postal_code=_present("520 001", "520001"),
    )


def test_initialization_creates_extracted_fields_table(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'extracted_fields'
            """
        ).fetchone()

    assert table == ("extracted_fields",)


def test_extracted_fields_round_trip_keeps_raw_and_normalized_distinct(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)
    _seed_case(db_path)

    assert save_extracted_fields(db_path, "CASE-DB03-001", _db03_fields()) == 7

    loaded = load_extracted_fields(db_path, "CASE-DB03-001")

    assert set(loaded.keys()) == {
        "customer_name",
        "address",
        "document_type",
        "document_date",
        "issuer_name",
        "document_number",
        "postal_code",
    }
    assert loaded["customer_name"]["raw_value"] == "  AARAV Mehta "
    assert loaded["customer_name"]["normalized_value"] == "aarav mehta"
    assert loaded["customer_name"]["raw_value"] != loaded["customer_name"]["normalized_value"]
    assert loaded["postal_code"]["raw_value"] == "520 001"
    assert loaded["postal_code"]["normalized_value"] == "520001"
    assert loaded["document_type"]["status"] == "missing"
    assert loaded["document_type"]["raw_value"] is None


def test_extracted_fields_save_is_idempotent_upsert(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)
    _seed_case(db_path)

    save_extracted_fields(db_path, "CASE-DB03-001", _db03_fields())
    save_extracted_fields(db_path, "CASE-DB03-001", _db03_fields())

    with sqlite3.connect(db_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM extracted_fields WHERE case_id = ?",
            ("CASE-DB03-001",),
        ).fetchone()[0]

    assert count == 7


def test_extracted_fields_reject_invalid_status(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)
    _seed_case(db_path)

    with sqlite3.connect(db_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO extracted_fields (
                    case_id,
                    field_name,
                    status
                )
                VALUES (?, ?, ?)
                """,
                ("CASE-DB03-001", "customer_name", "guessed"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Invalid field status was accepted")


def test_load_missing_case_is_explicit(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with pytest.raises(RepositoryError) as exc_info:
        load_extracted_fields(db_path, "CASE-NOPE")

    assert exc_info.value.code == "FIELDS_NOT_FOUND"


def test_extracted_fields_survive_restart(tmp_path: Path):
    db_path = tmp_path / "persistent.db"

    initialize_database(db_path)
    _seed_case(db_path)
    save_extracted_fields(db_path, "CASE-DB03-001", _db03_fields())

    loaded = load_extracted_fields(db_path, "CASE-DB03-001")

    assert loaded["address"]["normalized_value"] == "42 example avenue, vijayawada"


# ---------------------------------------------------------------------------
# DB-04: findings table (DoD: round-trip with provenance; every triggered
# indicator storable and retrievable)
# ---------------------------------------------------------------------------

from app.db.repository import (  # noqa: E402
    load_findings,
    save_findings,
)


def _db04_pipeline(kind: str = "name"):
    from app.document.field_parser import parse_fields as _parse
    from app.verification.compare import compare_fields as _compare
    from app.verification.normalize import normalize_fields as _nf
    from app.verification.risk_rules import assess_risk as _assess
    from app.verification.validate import validate_fields as _validate

    texts = {
        "name": "Customer Name\nAarav Sharma\nAddress\n42 Example Avenue, Vijayawada\nPostal Code\n520001",
    }
    ref = {
        "customer_id": "CUST-0001",
        "customer_name": "Aarav Mehta",
        "address": "42 Example Avenue, Vijayawada",
        "postal_code": "520001",
    }
    normalized = _nf(_parse(texts[kind]).fields)
    findings = _validate(normalized)
    comparisons = _compare(normalized, ref)
    indicators = _assess(findings, comparisons)
    return findings, comparisons, indicators


def test_initialization_creates_findings_table(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'findings'
            """
        ).fetchone()

    assert table == ("findings",)


def test_triggered_indicators_round_trip_with_provenance(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)
    _seed_case(db_path, case_id="CASE-DB04-001")

    findings, comparisons, indicators = _db04_pipeline()
    assert indicators, "expected at least one triggered indicator"

    count = save_findings(
        db_path,
        "CASE-DB04-001",
        findings=findings,
        comparisons=comparisons,
        indicators=indicators,
    )

    loaded = load_findings(db_path, "CASE-DB04-001")

    assert len(loaded) == count
    stored = {(row["kind"], row["ref"], row["code"]) for row in loaded}
    for indicator in indicators:
        assert ("indicator", indicator.indicator_code, indicator.indicator_code) in stored

    name_row = next(r for r in loaded if r["ref"] == "name_mismatch")
    assert name_row["rule_id"] == "RISK-001"
    assert name_row["rule_version"] == "1.0.0"
    assert name_row["severity"] == "warning"
    assert name_row["category"] == "verification_mismatch"
    assert name_row["reason"]

    comparison_row = next(
        r for r in loaded if r["kind"] == "comparison" and r["ref"] == "customer_name"
    )
    assert comparison_row["observed_value"] == "aarav sharma"
    assert comparison_row["reference_value"] == "aarav mehta"


def test_findings_reject_invalid_kind(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)
    _seed_case(db_path)

    with sqlite3.connect(db_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO findings (case_id, kind, ref, code)
                VALUES (?, ?, ?, ?)
                """,
                ("CASE-DB03-001", "guess", "x", "y"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Invalid finding kind was accepted")


def test_load_missing_findings_is_explicit(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with pytest.raises(RepositoryError) as exc_info:
        load_findings(db_path, "CASE-NOPE")

    assert exc_info.value.code == "FINDINGS_NOT_FOUND"


# ---------------------------------------------------------------------------
# DB-05: ai_results table (DoD: round-trip passes; AI metadata retrievable
# by case_id)
# ---------------------------------------------------------------------------

from app.db.repository import (  # noqa: E402
    load_ai_result,
    save_ai_result,
)


def _seed_ai_case(db_path: Path, case_id: str = "CASE-DB05-001"):
    _seed_case(db_path, case_id=case_id)


def test_initialization_creates_ai_results_table(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'ai_results'
            """
        ).fetchone()

    assert table == ("ai_results",)


def test_ai_result_round_trip_by_case_id(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)
    _seed_ai_case(db_path)

    refs = [
        {"source_id": "POL-RISK-001", "version": "1.0.0", "chunk_id": "POL-RISK-001#chunk-001"}
    ]
    save_ai_result(
        db_path,
        "CASE-DB05-001",
        ml_classification="mismatch_detected",
        model_version="1.0.0",
        retrieval_status="evidence_found",
        evidence_refs=refs,
        explanation_status="available",
        explanation_text="Name differs from reference.",
    )

    loaded = load_ai_result(db_path, "CASE-DB05-001")

    assert loaded["ml_classification"] == "mismatch_detected"
    assert loaded["model_version"] == "1.0.0"
    assert loaded["retrieval_status"] == "evidence_found"
    assert loaded["evidence_refs"] == refs
    assert loaded["explanation_status"] == "available"
    assert loaded["explanation_text"] == "Name differs from reference."


def test_ai_result_rejects_invalid_classification(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)
    _seed_ai_case(db_path)

    with sqlite3.connect(db_path) as connection:
        try:
            connection.execute(
                """
                INSERT INTO ai_results (
                    case_id,
                    ml_classification,
                    model_version,
                    retrieval_status,
                    explanation_status
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                ("CASE-DB05-001", "guessed", "1.0.0", "evidence_found", "available"),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Invalid ML classification was accepted")


def test_ai_result_save_validates_contracts(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)
    _seed_ai_case(db_path)

    with pytest.raises(RepositoryError) as exc_info:
        save_ai_result(
            db_path,
            "CASE-DB05-001",
            ml_classification="mismatch_detected",
            model_version="1.0.0",
            retrieval_status="evidence_found",
            evidence_refs=[{"source_id": "POL-RISK-001"}],
            explanation_status="available",
        )
    assert exc_info.value.code == "INVALID_EVIDENCE_REF"


def test_load_missing_ai_result_is_explicit(tmp_path: Path):
    db_path = tmp_path / "test.db"

    initialize_database(db_path)

    with pytest.raises(RepositoryError) as exc_info:
        load_ai_result(db_path, "CASE-NOPE")

    assert exc_info.value.code == "AI_RESULT_NOT_FOUND"