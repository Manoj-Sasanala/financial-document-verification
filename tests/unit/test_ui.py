"""UI-01 verification: upload/review page shell.

DoD: Upload request reaches the backend and handles validation errors.
Test: Page can send a valid multipart request (form contract matches the
API-05 endpoint, verified live via TestClient).
"""

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.db.init_db import initialize_database
from app.main import app
from scripts.seed_db import seed_customers

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HTML_PATH = PROJECT_ROOT / "app" / "ui" / "templates" / "review.html"
JS_PATH = PROJECT_ROOT / "app" / "ui" / "static" / "app.js"
CSS_PATH = PROJECT_ROOT / "app" / "ui" / "static" / "app.css"


def _html() -> str:
    return HTML_PATH.read_text(encoding="utf-8")


def test_shell_files_exist() -> None:
    assert HTML_PATH.is_file()
    assert JS_PATH.is_file()
    assert CSS_PATH.is_file()


def test_form_posts_valid_multipart_request() -> None:
    html = _html()

    assert 'action="/api/v1/cases"' in html
    assert 'method="post"' in html
    assert 'enctype="multipart/form-data"' in html
    assert 'name="customer_id"' in html
    assert 'name="file"' in html
    assert 'type="file"' in html


def test_client_script_wires_upload_and_errors() -> None:
    js = JS_PATH.read_text(encoding="utf-8")

    assert "FormData" in js
    assert "fetch(" in js
    assert "detail" in js
    assert CSS_PATH.read_text(encoding="utf-8").strip() != ""


def test_form_contract_matches_backend(tmp_path: Path) -> None:
    db_path = tmp_path / "ui.db"
    initialize_database(db_path)
    seed_customers(db_path)
    os.environ["CASE_DB_PATH"] = str(db_path)
    client = TestClient(app)

    pdf = (PROJECT_ROOT / "data" / "synthetic" / "documents" / "template.pdf").read_bytes()
    response = client.post(
        "/api/v1/cases",
        data={"customer_id": "CUST-0001"},
        files={"file": ("proof.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201

    bad = client.post(
        "/api/v1/cases",
        data={"customer_id": "CUST-0001"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert bad.status_code == 400
    assert "detail" in bad.json()
