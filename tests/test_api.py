from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_application_imports():
    assert app.title == "AI KYC Document Verification & Risk Copilot"
    assert app.version == "0.1.0"


def test_openapi_is_available():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "AI KYC Document Verification & Risk Copilot"


def test_swagger_ui_is_available():
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower()

def test_health_endpoint():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
