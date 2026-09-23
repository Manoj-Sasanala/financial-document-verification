"""RAG-06: Policy retrieval.

Retrieves relevant policy evidence for a case from the RAG-04 index using
RAG-05 queries. Returns the frozen ``RetrievalResult`` contract:
``evidence_found`` with ranked ``PolicyEvidence`` records, or a controlled
``no_evidence`` result — never an exception for low-similarity queries.

Boundaries (frozen for RAG-06):
  * Cosine (inner-product over normalized vectors) top-k search, default k=3.
  * ``MIN_SCORE = 0.25``: best score below threshold yields ``no_evidence``.
    Verified locally: real case queries score 0.4+, gibberish scores ~0.15.
  * Evidence identity (source_id/version/chunk_id) comes from the manifest
    chunk order; text and reference come from ``chunks.jsonl`` records.

Explicit failure states use :class:`RetrievalError` with a stable ``code``.

Consumer: LLM explanation; reviewer UI; persistence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.contracts import PolicyEvidence, RetrievalResult
from app.rag.query_builder import RetrievalQuery

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INDEX_PATH = PROJECT_ROOT / "artifacts" / "rag" / "faiss.index"
CHUNKS_PATH = PROJECT_ROOT / "artifacts" / "rag" / "chunks.jsonl"
METADATA_PATH = PROJECT_ROOT / "artifacts" / "rag" / "metadata.json"

MIN_SCORE = 0.25
DEFAULT_TOP_K = 3
TASK_ID = "RAG-06"


class RetrievalError(ValueError):
    """Controlled retrieval failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _require_runtime():
    try:
        import faiss
        import numpy as np
    except ImportError as exc:
        raise RetrievalError(
            "MISSING_DEPENDENCY",
            "faiss-cpu and numpy are required. Install with: pip install faiss-cpu numpy",
        ) from exc
    return faiss, np


def load_retrieval_context(
    index_path: Path | str = INDEX_PATH,
    chunks_path: Path | str = CHUNKS_PATH,
    metadata_path: Path | str = METADATA_PATH,
) -> dict[str, Any]:
    """Load index, chunk records and ordered chunk ids together."""
    from app.rag.index import load_index

    _, np = _require_runtime()
    try:
        index = load_index(index_path)
    except Exception as exc:
        code = getattr(exc, "code", "INDEX_UNAVAILABLE")
        raise RetrievalError(code, f"Retrieval index unavailable: {exc}") from exc
    try:
        import json

        chunk_records = [
            json.loads(line)
            for line in Path(chunks_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise RetrievalError("CONTEXT_UNREADABLE", f"Cannot load retrieval context: {exc}") from exc
    by_id = {record["chunk_id"]: record for record in chunk_records}
    ordered_ids: list[str] = metadata.get("chunk_ids", [r["chunk_id"] for r in chunk_records])
    if index.ntotal != len(ordered_ids):
        raise RetrievalError(
            "COUNT_MISMATCH", "Index rows do not match chunk id list."
        )
    return {"index": index, "by_id": by_id, "chunk_ids": ordered_ids, "numpy": np}


def embed_query_text(query_text: str):
    """Embed one query string with the fixed RAG-03 model."""
    from app.rag.embeddings import load_model

    if not isinstance(query_text, str) or not query_text.strip():
        raise RetrievalError("EMPTY_QUERY", "query_text must be non-empty.")
    _, np = _require_runtime()
    model = load_model()
    vector = model.encode([query_text], normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vector, dtype="float32")


def retrieve(
    query: RetrievalQuery,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_SCORE,
    context: dict[str, Any] | None = None,
) -> RetrievalResult:
    """Retrieve ranked policy evidence for a built query."""
    if not isinstance(query, RetrievalQuery):
        raise RetrievalError("INVALID_QUERY", "query must be a RetrievalQuery.")
    if top_k < 1:
        raise RetrievalError("INVALID_TOP_K", "top_k must be >= 1.")

    ctx = context if context is not None else load_retrieval_context()
    vector = embed_query_text(query.query_text)
    scores, positions = ctx["index"].search(vector, min(top_k, ctx["index"].ntotal))

    evidence: list[PolicyEvidence] = []
    for score, position in zip(scores[0].tolist(), positions[0].tolist()):
        if float(score) < min_score:
            continue
        chunk_id = ctx["chunk_ids"][int(position)]
        record = ctx["by_id"].get(chunk_id)
        if record is None:
            continue
        evidence.append(
            PolicyEvidence(
                source_id=record["source_id"],
                version=record["version"],
                chunk_id=chunk_id,
                text=record["text"],
                reference=record["source_path"],
            )
        )
    if not evidence:
        return RetrievalResult(status="no_evidence", evidence=[])
    return RetrievalResult(status="evidence_found", evidence=evidence)


def retrieve_with_boundary(
    query: RetrievalQuery,
    findings: list,
    indicators: list,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_SCORE,
    context: dict[str, Any] | None = None,
):
    """Retrieve evidence with the VER-06 read-only boundary enforced.

    Seals the deterministic VER-05 outputs before retrieval and proves them
    unchanged afterwards: replacing or altering retrieved evidence cannot
    change findings or indicators. Returns ``(sealed, result)``.
    """
    from app.verification.boundary import assert_unchanged, seal_verification

    sealed = seal_verification(findings, indicators)
    result = retrieve(query, top_k=top_k, min_score=min_score, context=context)
    assert_unchanged(sealed, findings, indicators)
    return sealed, result


__all__ = [
    "RetrievalError",
    "embed_query_text",
    "load_retrieval_context",
    "retrieve",
    "retrieve_with_boundary",
    "CHUNKS_PATH",
    "DEFAULT_TOP_K",
    "INDEX_PATH",
    "METADATA_PATH",
    "MIN_SCORE",
    "TASK_ID",
]
