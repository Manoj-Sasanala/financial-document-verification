"""QA-06 verification: persistence across restart.

DoD: Restart/retrieve test passes using the actual demo storage configuration.
Test: case_id returns identical stored results after restart.
"""

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.init_db import initialize_database
from app.main import app
from scripts.seed_db import seed_customers

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _create_case(client: TestClient) -> str:
    pdf = (PROJECT_ROOT / "data" / "synthetic" / "documents" / "template.pdf").read_bytes()
    response = client.post(
        "/api/v1/cases",
        data={"customer_id": "CUST-0001"},
        files={"file": ("proof.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()["case_id"]


def test_case_retrievable_after_app_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "restart.db"
    initialize_database(db_path)
    seed_customers(db_path)
    os.environ["CASE_DB_PATH"] = str(db_path)

    case_id = _create_case(TestClient(app))
    before = TestClient(app).get(f"/api/v1/cases/{case_id}").json()

    # Simulate an application restart: brand-new client, same database file.
    restarted = TestClient(app)
    after = restarted.get(f"/api/v1/cases/{case_id}")

    assert after.status_code == 200
    assert after.json() == before
    assert after.json()["fields"]["customer_name"]["raw_value"] == "Aarav Mehta"


def test_review_survives_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "restart-review.db"
    initialize_database(db_path)
    seed_customers(db_path)
    os.environ["CASE_DB_PATH"] = str(db_path)

    case_id = _create_case(TestClient(app))
    assert TestClient(app).post(
        f"/api/v1/cases/{case_id}/review",
        json={"decision": "approve", "comment": "Restart check."},
    ).status_code == 200

    reloaded = TestClient(app).get(f"/api/v1/cases/{case_id}").json()

    assert reloaded["review"]["decision"] == "approve"
    assert reloaded["review"]["comment"] == "Restart check."


def test_storage_configuration_is_documented() -> None:
    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "CASE_DB_PATH" in example
