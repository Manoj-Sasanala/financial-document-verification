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


# ---------------------------------------------------------------------------
# DEP-02: Persistent SQLite storage (DoD: demo deployment passes persistence
# test; stored case survives service restart)
# ---------------------------------------------------------------------------


def _boot_server(db_path: Path, port: int):
    import socket
    import subprocess
    import sys

    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0
    env = {
        **os.environ,
        "CASE_DB_PATH": str(db_path),
        "LLM_API_KEY": "",
    }
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc


def _wait_healthy(port: int, timeout_s: float = 120.0) -> None:
    import time
    import urllib.request

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/v1/health", timeout=5
            ) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(2)
    raise AssertionError("service did not become healthy in time")


def _compose_configures_persistent_volume() -> None:
    text = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "CASE_DB_PATH" in text
    assert "kyc-data:/data" in text


def test_stored_case_survives_service_restart(tmp_path: Path) -> None:
    import socket
    import urllib.request

    _compose_configures_persistent_volume()
    db_path = tmp_path / "svc.db"
    initialize_database(db_path)
    seed_customers(db_path)

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    pdf = (PROJECT_ROOT / "data" / "synthetic" / "documents" / "template.pdf").read_bytes()

    def _post_case() -> str:
        import io
        import uuid

        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"customer_id\"\r\n\r\n"
            f"CUST-0001\r\n--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="proof.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode() + pdf + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/cases",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read().decode("utf-8")
        import json as _json

        return _json.loads(payload)["case_id"]

    def _get_case(case_id: str) -> str:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/cases/{case_id}", timeout=30
        ) as response:
            return response.read().decode("utf-8")

    server = _boot_server(db_path, port)
    try:
        _wait_healthy(port)
        case_id = _post_case()
        before = _get_case(case_id)
    finally:
        server.terminate()
        server.wait(timeout=30)

    rebooted = _boot_server(db_path, port)
    try:
        _wait_healthy(port)
        after = _get_case(case_id)
    finally:
        rebooted.terminate()
        rebooted.wait(timeout=30)

    assert after == before
    assert '"Aarav Mehta"' in after
