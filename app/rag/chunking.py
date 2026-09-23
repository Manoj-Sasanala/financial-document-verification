"""RAG-02: Chunk policy corpus.

Prepares DATA-07 policy text for retrieval using the RAG-01 metadata schema.

Chunking boundary (frozen, shared with RAG-01):
  * One chunk per markdown ``## `` section, in document order.
  * ``chunk_id`` format: ``{source_id}#chunk-{index:03d}``.

Canonical output:
  artifacts/rag/chunks.jsonl  (one chunk record per line)

Each record carries chunk text plus stable source metadata
(``source_id`` / ``version`` / ``title`` / ``chunk_id``) and provenance so
the embedding/index builder (RAG-03/RAG-04) consumes a reproducible input.

Explicit failure states reuse :class:`MetadataError` codes from
:mod:`app.rag.metadata`.

Consumer: embedding/index builder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.rag.metadata import (
    MANIFEST_PATH,
    MetadataError,
    PolicyChunkMetadata,
    build_chunk_index,
    load_manifest,
    validate_source_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CHUNKS_PATH = PROJECT_ROOT / "artifacts" / "rag" / "chunks.jsonl"

SCHEMA_VERSION = "1.0.0"
TASK_ID = "RAG-02"
GENERATOR = "rag-chunking/1.0.0"

REQUIRED_CHUNK_FIELDS = (
    "chunk_id",
    "source_id",
    "version",
    "title",
    "section_heading",
    "chunk_index",
    "text",
    "char_start",
    "char_end",
    "source_path",
    "provenance",
)


def build_chunks(
    manifest_path: Path | str = MANIFEST_PATH, repo_root: Path = PROJECT_ROOT
) -> list[dict[str, Any]]:
    """Build every chunk record (metadata + text slice) for the corpus."""
    manifest = load_manifest(manifest_path)
    items_by_id = {item.source_id: item for item in manifest.items}
    records: list[dict[str, Any]] = []

    for chunk in build_chunk_index(manifest_path, repo_root):
        content = validate_source_file(items_by_id[chunk.source_id], repo_root)
        text = content[chunk.char_start : chunk.char_end].strip()
        if not text:
            raise MetadataError("EMPTY_CHUNK", f"Chunk text is empty: {chunk.chunk_id}")
        records.append(chunk_record(chunk, text, manifest.corpus_id, manifest.corpus_version))
    return records


def chunk_record(
    chunk: PolicyChunkMetadata, text: str, corpus_id: str, corpus_version: str
) -> dict[str, Any]:
    """Project one chunk + text slice onto the frozen chunk record shape."""
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "version": chunk.version,
        "title": chunk.title,
        "section_heading": chunk.section_heading,
        "chunk_index": chunk.chunk_index,
        "text": text,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "source_path": chunk.source_path,
        "provenance": {
            "task_id": TASK_ID,
            "schema_version": SCHEMA_VERSION,
            "generator": GENERATOR,
            "corpus_id": corpus_id,
            "corpus_version": corpus_version,
            "source_manifest": "data/policy/manifest.json",
        },
    }


def write_chunks_jsonl(path: Path | str, records: list[dict[str, Any]]) -> Path:
    """Write chunk records deterministically (one per line, document order)."""
    out = Path(path)
    if not records:
        raise MetadataError("EMPTY_CORPUS", f"No chunk records to write: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("w", encoding="utf-8") as fh:
            for record in records:
                missing = [f for f in REQUIRED_CHUNK_FIELDS if f not in record]
                if missing:
                    raise MetadataError(
                        "INVALID_CHUNK_RECORD",
                        f"Chunk {record.get('chunk_id', '?')} missing fields: {missing}",
                    )
                fh.write(json.dumps(record, sort_keys=False) + "\n")
    except MetadataError:
        raise
    except Exception as exc:
        raise MetadataError("WRITE_FAILED", f"Failed to write {out}: {exc}") from exc
    return out


def read_chunks_jsonl(path: Path | str = CHUNKS_PATH) -> list[dict[str, Any]]:
    """Read a chunk manifest (one record per line); skips blank lines."""
    src = Path(path)
    if not src.is_file():
        raise MetadataError("CHUNKS_NOT_FOUND", f"Chunk manifest not found: {src}")
    records: list[dict[str, Any]] = []
    with src.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MetadataError(
                    "INVALID_CHUNKS_JSONL", f"Invalid JSON on line {lineno} of {src}: {exc}"
                ) from exc
            if not isinstance(obj, dict):
                raise MetadataError(
                    "INVALID_CHUNK_RECORD", f"Line {lineno} of {src} must be a JSON object"
                )
            records.append(obj)
    if not records:
        raise MetadataError("EMPTY_CORPUS", f"Chunk manifest is empty: {src}")
    return records


def main() -> Path:
    """Rebuild the canonical chunk manifest from the policy corpus."""
    records = build_chunks()
    out = write_chunks_jsonl(CHUNKS_PATH, records)
    print(f"Wrote {len(records)} chunks -> {out.relative_to(PROJECT_ROOT).as_posix()}")
    return out


if __name__ == "__main__":
    main()


__all__ = [
    "build_chunks",
    "chunk_record",
    "read_chunks_jsonl",
    "write_chunks_jsonl",
    "main",
    "CHUNKS_PATH",
    "REQUIRED_CHUNK_FIELDS",
    "SCHEMA_VERSION",
    "TASK_ID",
]
