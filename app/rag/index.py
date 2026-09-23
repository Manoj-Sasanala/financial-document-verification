"""RAG-04: FAISS index.

Enables local similarity retrieval over RAG-03 embeddings without a
separate vector database.

Boundaries (frozen for RAG-04):
  * Flat inner-product index (``IndexFlatIP``) over L2-normalized vectors,
    i.e. exact cosine-similarity search — deterministic, no training step.
  * Position ``i`` in the index always corresponds to ``chunk_ids[i]`` from
    ``artifacts/rag/metadata.json`` (manifest order).
  * ``artifacts/rag/faiss.index`` is the persisted index; ``metadata.json``
    gains an ``index`` section (type, metric, count, faiss version).

Explicit failure states use :class:`IndexError` with a stable ``code``.

Consumer: runtime retriever (RAG-06).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

EMBEDDINGS_PATH = PROJECT_ROOT / "artifacts" / "rag" / "embeddings.npy"
METADATA_PATH = PROJECT_ROOT / "artifacts" / "rag" / "metadata.json"
INDEX_PATH = PROJECT_ROOT / "artifacts" / "rag" / "faiss.index"

INDEX_TYPE = "IndexFlatIP"
METRIC = "cosine-via-inner-product"
TASK_ID = "RAG-04"


class IndexError(ValueError):
    """Controlled index failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _require_faiss():
    try:
        import faiss
        import numpy as np
    except ImportError as exc:
        raise IndexError(
            "MISSING_DEPENDENCY",
            "faiss-cpu and numpy are required. Install with: pip install faiss-cpu numpy",
        ) from exc
    return faiss, np


def load_matrix(embeddings_path: Path | str = EMBEDDINGS_PATH):
    """Load the embedding matrix, validating shape and dtype."""
    _, np = _require_faiss()
    src = Path(embeddings_path)
    if not src.is_file():
        raise IndexError("EMBEDDINGS_MISSING", f"Embeddings not found: {src}")
    try:
        matrix = np.load(src)
    except Exception as exc:
        raise IndexError("EMBEDDINGS_UNREADABLE", f"Cannot load {src}: {exc}") from exc
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise IndexError("BAD_SHAPE", f"Unexpected embedding shape {matrix.shape}.")
    return np.ascontiguousarray(matrix, dtype="float32")


def build_index(matrix=None, embeddings_path: Path | str = EMBEDDINGS_PATH):
    """Build the flat inner-product index over the embedding matrix."""
    faiss, _ = _require_faiss()
    vectors = load_matrix(embeddings_path) if matrix is None else matrix
    index = faiss.IndexFlatIP(int(vectors.shape[1]))
    index.add(vectors)
    if index.ntotal != vectors.shape[0]:
        raise IndexError("BUILD_FAILED", "Index count does not match matrix rows.")
    return index


def save_index(index, path: Path | str = INDEX_PATH) -> Path:
    """Persist the index to disk."""
    faiss, _ = _require_faiss()
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        faiss.write_index(index, str(out))
    except Exception as exc:
        raise IndexError("WRITE_FAILED", f"Cannot write {out}: {exc}") from exc
    return out


def load_index(path: Path | str = INDEX_PATH):
    """Load a persisted index, validating row count against metadata."""
    faiss, _ = _require_faiss()
    src = Path(path)
    if not src.is_file():
        raise IndexError("INDEX_MISSING", f"FAISS index not found: {src}")
    try:
        index = faiss.read_index(str(src))
    except Exception as exc:
        raise IndexError("INDEX_UNREADABLE", f"Cannot read {src}: {exc}") from exc
    try:
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise IndexError("METADATA_MISSING", f"Cannot read index metadata: {exc}") from exc
    expected = metadata.get("num_chunks")
    if expected is not None and index.ntotal != expected:
        raise IndexError(
            "COUNT_MISMATCH",
            f"Index holds {index.ntotal} vectors but metadata expects {expected}.",
        )
    return index


def record_index_metadata(
    index, metadata_path: Path | str = METADATA_PATH
) -> dict[str, Any]:
    """Record index provenance in metadata.json; return the index section."""
    faiss, _ = _require_faiss()
    path = Path(metadata_path)
    if not path.is_file():
        raise IndexError("METADATA_MISSING", f"metadata.json not found: {path}")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    try:
        faiss_version: str | None = faiss.__version__
    except AttributeError:
        faiss_version = None
    metadata["index"] = {
        "task_id": TASK_ID,
        "type": INDEX_TYPE,
        "metric": METRIC,
        "ntotal": int(index.ntotal),
        "dim": int(index.d),
        "faiss_version": faiss_version,
        "path": "artifacts/rag/faiss.index",
    }
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata["index"]


def build_and_save(
    embeddings_path: Path | str = EMBEDDINGS_PATH,
    index_path: Path | str = INDEX_PATH,
    metadata_path: Path | str = METADATA_PATH,
):
    """Build the index from canonical embeddings and persist it + metadata."""
    index = build_index(embeddings_path=embeddings_path)
    out = save_index(index, index_path)
    section = record_index_metadata(index, metadata_path)
    print(
        f"Indexed {section['ntotal']} vectors (dim {section['dim']}) "
        f"-> {out.relative_to(PROJECT_ROOT).as_posix()}"
    )
    return index


__all__ = [
    "IndexError",
    "build_and_save",
    "build_index",
    "load_index",
    "load_matrix",
    "record_index_metadata",
    "save_index",
    "EMBEDDINGS_PATH",
    "INDEX_PATH",
    "INDEX_TYPE",
    "METADATA_PATH",
    "METRIC",
    "TASK_ID",
]
