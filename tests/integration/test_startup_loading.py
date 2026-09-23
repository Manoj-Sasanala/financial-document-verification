"""QA-07 verification: ML/RAG artifacts load once.

DoD: Logs/tests confirm one startup load path.
Test: Multiple requests reuse loaded artifacts without rebuilding.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.startup import RuntimeState, load_runtime


def test_startup_loads_all_artifacts_once() -> None:
    with TestClient(app) as client:
        runtime = client.app.state.runtime

        assert isinstance(runtime, RuntimeState)
        assert runtime.errors == []
        assert runtime.is_ready() is True
        assert runtime.ml_model.model_version == "1.0.0"
        assert runtime.retrieval_context["index"].ntotal == 35


def test_requests_reuse_loaded_artifacts_without_rebuilding() -> None:
    with TestClient(app) as client:
        first_ml = client.app.state.runtime.ml_model
        first_index = client.app.state.runtime.retrieval_context["index"]

        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/openapi.json").status_code == 200

        assert client.app.state.runtime.ml_model is first_ml
        assert client.app.state.runtime.retrieval_context["index"] is first_index


def test_missing_artifacts_start_degraded_with_errors() -> None:
    runtime = load_runtime(artifacts_ml="artifacts/nope-ml", artifacts_rag="artifacts/nope-rag")

    assert runtime.is_ready() is False
    assert runtime.ml_model is None
    assert runtime.retrieval_context is None
    assert any(e.startswith("ml:") for e in runtime.errors)
    assert any(e.startswith("retrieval:") for e in runtime.errors)
