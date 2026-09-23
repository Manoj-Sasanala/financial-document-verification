"""RAG-03: Local embeddings.

Creates semantic vectors for RAG-02 policy chunks with one fixed embedding
model: ``sentence-transformers/all-MiniLM-L6-v2`` (384 dimensions).

Boundaries (frozen for RAG-03):
  * Vectors are L2-normalized float32 so the FAISS index (RAG-04) can use
    inner-product search as cosine similarity.
  * Row order always matches ``artifacts/rag/chunks.jsonl`` line order; the
    chunk_id list is persisted alongside for alignment checks.
  * ``artifacts/rag/metadata.json`` records the model id, embedding dim,
    chunk count, chunk manifest hash and library versions.

Canonical outputs: ``artifacts/rag/embeddings.npy`` + ``artifacts/rag/metadata.json``.

Explicit failure states use :class:`EmbeddingError` with a stable ``code``.

Consumer: FAISS index (RAG-04).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CHUNKS_PATH = PROJECT_ROOT / "artifacts" / "rag" / "chunks.jsonl"
EMBEDDINGS_PATH = PROJECT_ROOT / "artifacts" / "rag" / "embeddings.npy"
METADATA_PATH = PROJECT_ROOT / "artifacts" / "rag" / "metadata.json"

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
TASK_ID = "RAG-03"


class EmbeddingError(ValueError):
    """Controlled embedding failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _require_runtime():
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingError(
            "MISSING_DEPENDENCY",
            "sentence-transformers, torch and numpy are required. "
            "Install with: pip install sentence-transformers torch numpy",
        ) from exc
    return np, SentenceTransformer


def load_model(model_id: str = MODEL_ID):
    """Load the fixed embedding model (uses the local HF cache offline)."""
    _, SentenceTransformer = _require_runtime()
    try:
        return SentenceTransformer(model_id)
    except Exception as exc:
        raise EmbeddingError("MODEL_LOAD_FAILED", f"Cannot load {model_id}: {exc}") from exc


def read_chunk_texts(chunks_path: Path | str = CHUNKS_PATH) -> tuple[list[str], list[str]]:
    """Return (chunk_id list, text list) in manifest order."""
    from app.rag.chunking import read_chunks_jsonl

    try:
        records = read_chunks_jsonl(chunks_path)
    except Exception as exc:
        code = getattr(exc, "code", "CHUNKS_UNREADABLE")
        raise EmbeddingError(code, f"Cannot read chunk manifest: {exc}") from exc
    ids = [r["chunk_id"] for r in records]
    texts = [f"{r['section_heading']}\n{r['text']}" for r in records]
    return ids, texts


def embed_texts(texts: list[str], model=None):
    """Encode texts to L2-normalized float32 vectors (deterministic)."""
    np, _ = _require_runtime()
    if not texts:
        raise EmbeddingError("EMPTY_CHUNKS", "No chunk texts to embed.")
    owned = False
    if model is None:
        model = load_model()
        owned = True
    try:
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    except Exception as exc:
        raise EmbeddingError("ENCODING_FAILED", f"Embedding failed: {exc}") from exc
    finally:
        _ = owned
    array = np.asarray(vectors, dtype="float32")
    if array.ndim != 2 or array.shape[0] != len(texts):
        raise EmbeddingError("BAD_SHAPE", f"Unexpected embedding shape {array.shape}.")
    return array


def _library_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in ("sentence_transformers", "transformers", "tokenizers", "torch", "numpy"):
        try:
            module = __import__(name)
            versions[name] = getattr(module, "__version__", None)
        except ImportError:
            versions[name] = None
    return versions


def build_metadata(chunk_ids: list[str], chunks_path: Path | str = CHUNKS_PATH) -> dict[str, Any]:
    """Model + corpus provenance for the embedding matrix."""
    manifest_hash = hashlib.sha256(Path(chunks_path).read_bytes()).hexdigest()
    return {
        "task_id": TASK_ID,
        "model_id": MODEL_ID,
        "embedding_dim": 384,
        "num_chunks": len(chunk_ids),
        "chunk_ids": chunk_ids,
        "chunks_manifest": "artifacts/rag/chunks.jsonl",
        "chunks_sha256": manifest_hash,
        "normalized": True,
        "dtype": "float32",
        "libraries": _library_versions(),
    }


def build_and_save(
    chunks_path: Path | str = CHUNKS_PATH,
    embeddings_path: Path | str = EMBEDDINGS_PATH,
    metadata_path: Path | str = METADATA_PATH,
) -> dict[str, Any]:
    """Embed the canonical chunks and persist matrix + metadata."""
    np, _ = _require_runtime()
    chunk_ids, texts = read_chunk_texts(chunks_path)
    model = load_model()
    matrix = embed_texts(texts, model)

    out_npy = Path(embeddings_path)
    out_npy.parent.mkdir(parents=True, exist_ok=True)
    try:
        np.save(out_npy, matrix)
    except OSError as exc:
        raise EmbeddingError("WRITE_FAILED", f"Cannot write {out_npy}: {exc}") from exc
    metadata = build_metadata(chunk_ids, chunks_path)
    Path(metadata_path).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(
        f"Embedded {matrix.shape[0]} chunks x {matrix.shape[1]} "
        f"-> {out_npy.relative_to(PROJECT_ROOT).as_posix()}"
    )
    return metadata


__all__ = [
    "EmbeddingError",
    "build_and_save",
    "build_metadata",
    "embed_texts",
    "load_model",
    "read_chunk_texts",
    "CHUNKS_PATH",
    "EMBEDDINGS_PATH",
    "METADATA_PATH",
    "MODEL_ID",
    "TASK_ID",
]
