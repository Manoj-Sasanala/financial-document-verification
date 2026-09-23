from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "db.sqlite3"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def initialize_database(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    """
    Create the SQLite database and initialize the schema.

    The operation is idempotent: running it multiple times does not
    recreate or destroy existing tables/data.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(db_path) as connection:
        connection.executescript(schema)

    return db_path


if __name__ == "__main__":
    database_path = initialize_database()
    print(f"Initialized SQLite database: {database_path}")