"""API-05 verification: case lifecycle endpoints.

DoD: All three endpoints implemented with frozen schemas, explicit failures,
and no recompute on retrieval.
Test: Clean synthetic case created, retrieved, reviewed, and retrieved again
with the stored decision.
"""

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.init_db import initialize_database
from app.main import app
from scripts.seed_db import seed_customers

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "api.db"
    initialize_database(db_path)
    seed_customers(db_path)
    os.environ["CASE_DB_PATH"] = str(db_path)
    return TestClient(app)


def _pdf_bytes() -> bytes:
    return (PROJECT_ROOT / "data" / "synthetic" / "documents" / "template.pdf").read_bytes()


def _create_case(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/cases",
        data={"customer_id": "CUST-0001"},
        files={"file": ("proof.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_clean_case_retrieve_review_retrieve(tmp_path: Path) -> None:
    client = _client(tmp_path)
    created = _create_case(client)
    case_id = created["case_id"]

    assert created["fields"]["customer_name"]["raw_value"] == "Aarav Mehta"
    assert created["status"] in {"completed", "completed_with_warnings"}

    retrieved = client.get(f"/api/v1/cases/{case_id}")
    assert retrieved.status_code == 200
    assert retrieved.json()["case_id"] == case_id
    assert retrieved.json()["fields"]["customer_name"]["raw_value"] == "Aarav Mehta"

    review = client.post(
        f"/api/v1/cases/{case_id}/review",
        json={"decision": "approve", "comment": "Verified."},
    )
    assert review.status_code == 200
    assert review.json()["decision"] == "approve"

    again = client.get(f"/api/v1/cases/{case_id}")
    assert again.status_code == 200
    assert again.json()["review"]["decision"] == "approve"
    assert again.json()["review"]["comment"] == "Verified."


def test_unknown_case_returns_404(tmp_path: Path) -> None:
    client = _client(tmp_path)

    assert client.get("/api/v1/cases/CASE-NOPE").status_code == 404
    assert client.post("/api/v1/cases/CASE-NOPE/review", json={"decision": "approve"}).status_code == 404


def test_invalid_review_decision_returns_422(tmp_path: Path) -> None:
    client = _client(tmp_path)
    case_id = _create_case(client)["case_id"]

    response = client.post(f"/api/v1/cases/{case_id}/review", json={"decision": "maybe"})

    assert response.status_code == 422


def test_unsupported_file_returns_400(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/api/v1/cases",
        data={"customer_id": "CUST-0001"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
