"""DEP-01 verification: single-service deployment boots.

DoD: Deployment starts and exposes the main endpoint.
Test: Service starts in a clean environment with required local artifacts.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_dockerfile_defines_single_service() -> None:
    content = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:" in content
    assert "requirements.txt" in content
    assert "uvicorn" in content
    assert "app.main:app" in content
    assert "EXPOSE 8000" in content


def test_service_boots_and_exposes_health() -> None:
    port = _free_port()
    env = {
        **os.environ,
        "CASE_DB_PATH": str(PROJECT_ROOT / "db.sqlite3"),
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
    try:
        deadline = time.time() + 120
        body = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/v1/health", timeout=5
                ) as response:
                    if response.status == 200:
                        body = response.read().decode("utf-8")
                        break
            except OSError:
                time.sleep(2)
        assert body is not None, "service did not expose /api/v1/health in time"
        assert '"ok"' in body
    finally:
        proc.terminate()
        proc.wait(timeout=30)
