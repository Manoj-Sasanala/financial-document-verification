"""QA-07: Startup loading.

Loads ML/RAG artifacts once at application startup so multiple requests
reuse the loaded objects without rebuilding:

  * ML-02 classifier artifacts (LoadedModel via ML-04 loader).
  * RAG-04 FAISS index + chunk retrieval context.

``load_runtime`` never raises: missing artifacts are recorded in
``errors`` and the app starts degraded (endpoints return controlled
failures). ``is_ready`` reports whether all artifacts loaded.

Consumer: runtime orchestrator (FastAPI lifespan in ``app/main.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TASK_ID = "QA-07"


@dataclass
class RuntimeState:
    """Once-loaded runtime artifacts shared across requests."""

    ml_model: Any = None
    retrieval_context: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)

    def is_ready(self) -> bool:
        """True only when every artifact loaded without errors."""
        return self.ml_model is not None and self.retrieval_context is not None


def load_runtime(
    artifacts_ml: Path | str | None = None,
    artifacts_rag: Path | str | None = None,
) -> RuntimeState:
    """Load all runtime artifacts once; record failures instead of raising."""
    from app.ml.inference import ARTIFACTS_DIR as _ML_DIR
    from app.ml.inference import load_artifacts

    state = RuntimeState()
    ml_dir = Path(artifacts_ml) if artifacts_ml is not None else Path(_ML_DIR)
    try:
        state.ml_model = load_artifacts(ml_dir)
    except Exception as exc:
        code = getattr(exc, "code", "LOAD_FAILED")
        state.errors.append(f"ml:{code}: {exc}")
    try:
        from app.rag.retriever import INDEX_PATH, load_retrieval_context

        rag_index = Path(artifacts_rag) / "faiss.index" if artifacts_rag else INDEX_PATH
        state.retrieval_context = load_retrieval_context(index_path=rag_index)
    except Exception as exc:
        code = getattr(exc, "code", "LOAD_FAILED")
        state.errors.append(f"retrieval:{code}: {exc}")
    return state


__all__ = ["RuntimeState", "load_runtime", "TASK_ID"]
