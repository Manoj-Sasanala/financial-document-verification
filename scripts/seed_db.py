import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Make the repository root importable when this file is executed directly:
# python scripts/seed_db.py
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.init_db import DEFAULT_DB_PATH, initialize_database  # noqa: E402


CUSTOMERS_PATH = PROJECT_ROOT / "data" / "synthetic" / "customers.json"


def seed_customers(
    db_path: str | Path = DEFAULT_DB_PATH,
    customers_path: str | Path = CUSTOMERS_PATH,
) -> int:
    """
    Seed synthetic customer reference records into SQLite.

    Existing customer IDs are updated so the seed operation is safe
    to run repeatedly without creating duplicate records.
    """
    db_path = initialize_database(db_path)
    customers_path = Path(customers_path)

    customers = json.loads(customers_path.read_text(encoding="utf-8"))

    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            """
            INSERT INTO customers (
                customer_id,
                customer_name,
                address,
                postal_code
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(customer_id) DO UPDATE SET
                customer_name = excluded.customer_name,
                address = excluded.address,
                postal_code = excluded.postal_code
            """,
            [
                (
                    customer["customer_id"],
                    customer["customer_name"],
                    customer["address"],
                    customer["postal_code"],
                )
                for customer in customers
            ],
        )

    return len(customers)


if __name__ == "__main__":
    count = seed_customers()
    print(f"Seeded {count} customer records.")