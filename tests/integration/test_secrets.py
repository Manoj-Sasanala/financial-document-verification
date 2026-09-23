"""API-07 verification: secrets stay server-side.

DoD: Secret handling verified by source/config inspection.
Test: Repository/frontend contains no secret value and API responses
contain no secret.
"""

import os
import re
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import load_llm_settings
from app.db.init_db import initialize_database
from app.main import app
from scripts.seed_db import seed_customers

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SENTINEL_KEY = "sk-test-sentinel-9f8e7d6c5b4a"


def test_env_example_declares_keys_without_values() -> None:
    example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    for name in ("LLM_API_KEY", "LLM_API_URL", "LLM_MODEL", "LLM_TIMEOUT_S"):
        assert name in example
    assert SENTINEL_KEY not in example
    key_lines = [line for line in example.splitlines() if line.startswith("LLM_API_KEY")]
    assert key_lines and all(line.split("=", 1)[1].strip() == "" for line in key_lines)


def test_no_env_file_is_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()

    assert ".env" not in tracked
    assert not any(name.startswith(".env.") and not name.endswith(".example") for name in tracked)

    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^\.env$", gitignore, re.MULTILINE)


def test_frontend_contains_no_secret() -> None:
    for relative in (
        "app/ui/templates/review.html",
        "app/ui/static/app.js",
        "app/ui/static/app.css",
    ):
        content = (PROJECT_ROOT / relative).read_text(encoding="utf-8")
        assert "sk-" not in content
        assert "LLM_API_KEY" not in content
        assert SENTINEL_KEY not in content


def test_settings_load_key_from_server_environment() -> None:
    os.environ["LLM_API_KEY"] = SENTINEL_KEY
    os.environ["LLM_MODEL"] = "sentinel-model"
    try:
        settings = load_llm_settings()
        assert settings.api_key == SENTINEL_KEY
        assert settings.model == "sentinel-model"
        assert settings.timeout_s > 0
    finally:
        del os.environ["LLM_API_KEY"]
        del os.environ["LLM_MODEL"]


def test_api_responses_contain_no_secret(tmp_path: Path) -> None:
    db_path = tmp_path / "secrets.db"
    initialize_database(db_path)
    seed_customers(db_path)
    os.environ["CASE_DB_PATH"] = str(db_path)
    os.environ["LLM_API_KEY"] = SENTINEL_KEY
    try:
        client = TestClient(app)
        pdf = (PROJECT_ROOT / "data" / "synthetic" / "documents" / "template.pdf").read_bytes()
        created = client.post(
            "/api/v1/cases",
            data={"customer_id": "CUST-0001"},
            files={"file": ("proof.pdf", pdf, "application/pdf")},
        )
        assert created.status_code == 201
        case_id = created.json()["case_id"]
        bodies = [
            created.text,
            client.get(f"/api/v1/cases/{case_id}").text,
            client.post(
                f"/api/v1/cases/{case_id}/review", json={"decision": "approve"}
            ).text,
            client.get("/api/v1/health").text,
            client.get("/openapi.json").text,
        ]
    finally:
        del os.environ["LLM_API_KEY"]
    for body in bodies:
        assert SENTINEL_KEY not in body
