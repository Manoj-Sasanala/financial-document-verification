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
