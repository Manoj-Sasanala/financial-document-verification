import json
import sqlite3
from pathlib import Path

from app.db.init_db import initialize_database
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