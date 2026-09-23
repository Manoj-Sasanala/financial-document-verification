"""RAG-01: Policy document metadata schema.

Standardizes source identity / version / chunk metadata for the DATA-07
controlled policy corpus (``data/policy/manifest.json`` + ``sources/``).

Frozen interface alignment (Step 9.6, ``app/core/contracts.py``):
  * ``PolicyEvidence`` requires ``source_id`` / ``version`` / ``chunk_id``.
  * This module defines how those three fields (plus ``title``) are formed,
    validated, and kept stable so the index builder and retrieval responses
    share one source of truth.

Chunking boundary (deterministic, frozen for RAG-01):
  * One chunk per markdown ``## `` section within a policy source file.
  * ``chunk_id`` format: ``{source_id}#chunk-{index:03d}`` where ``index``
    follows document order starting at 1.
  * Frontmatter lines and the ``# `` document title are structural context,
    not chunks.

Explicit failure states use :class:`MetadataError` with a stable ``code``.
Provenance (corpus id/version, source path, section heading, char span) is
preserved on every chunk record for downstream handoff.

Consumer: index builder; retrieval response.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MANIFEST_PATH = PROJECT_ROOT / "data" / "policy" / "manifest.json"
SOURCES_DIR = PROJECT_ROOT / "data" / "policy" / "sources"

SCHEMA_VERSION = "1.0.0"
TASK_ID = "RAG-01"

SOURCE_ID_PATTERN = re.compile(r"^POL-RISK-\d{3}$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
CHUNK_ID_PATTERN = re.compile(r"^POL-RISK-\d{3}#chunk-\d{3}$")


class MetadataError(ValueError):
    """Controlled metadata failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


class PolicySourceMetadata(BaseModel):
    """Identity/version metadata for one policy source document."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^POL-RISK-\d{3}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(min_length=1)
    path: str = Field(min_length=1)
    risk_indicator: str = Field(min_length=1)

    @field_validator("title", "path", "risk_indicator")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class PolicyChunkMetadata(BaseModel):
    """Stable chunk-level metadata for one section of a policy source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^POL-RISK-\d{3}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(min_length=1)
    chunk_id: str = Field(pattern=r"^POL-RISK-\d{3}#chunk-\d{3}$")
    chunk_index: int = Field(ge=1)
    section_heading: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=1)

    @field_validator("chunk_id")
    @classmethod
    def _chunk_id_matches_source(cls, value: str, info: Any) -> str:
        source_id = (info.data or {}).get("source_id")
        if source_id and not value.startswith(f"{source_id}#chunk-"):
            raise ValueError("chunk_id must start with '<source_id>#chunk-'")
        return value


class CorpusMetadata(BaseModel):
    """Top-level metadata for the controlled policy corpus manifest."""

    model_config = ConfigDict(extra="forbid")

    corpus_id: str = Field(min_length=1)
    corpus_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: str = Field(min_length=1)
    external_sources_allowed: bool
    items: list[PolicySourceMetadata] = Field(min_length=1)
    # Optional DATA-07 manifest fields: accepted and preserved, not required.
    description: str | None = None
    authority: str | None = None


def chunk_id_for(source_id: str, chunk_index: int) -> str:
    """Build the stable chunk_id for a 1-based section index."""
    if not SOURCE_ID_PATTERN.match(source_id):
        raise MetadataError("INVALID_SOURCE_ID", f"Invalid source_id: {source_id!r}")
    if chunk_index < 1:
        raise MetadataError("INVALID_CHUNK_INDEX", f"chunk_index must be >= 1, got {chunk_index}")
    return f"{source_id}#chunk-{chunk_index:03d}"


def load_manifest(manifest_path: Path | str = MANIFEST_PATH) -> CorpusMetadata:
    """Load and validate the policy corpus manifest."""
    path = Path(manifest_path)
    if not path.is_file():
        raise MetadataError("MANIFEST_NOT_FOUND", f"Policy manifest not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MetadataError("INVALID_MANIFEST_JSON", f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise MetadataError("INVALID_MANIFEST", f"Manifest must be a JSON object: {path}")
    try:
        manifest = CorpusMetadata.model_validate(raw)
    except Exception as exc:
        raise MetadataError("INVALID_MANIFEST", f"Manifest failed schema validation: {exc}") from exc

    source_ids = [item.source_id for item in manifest.items]
    duplicates = {sid for sid in source_ids if source_ids.count(sid) > 1}
    if duplicates:
        raise MetadataError(
            "DUPLICATE_SOURCE_ID", f"Duplicate source_id in manifest: {sorted(duplicates)}"
        )
    return manifest


def parse_frontmatter(content: str, source_path: Path) -> dict[str, str]:
    """Parse the ``---`` YAML-style frontmatter block of a policy source."""
    if not content.startswith("---"):
        raise MetadataError("MISSING_FRONTMATTER", f"Missing frontmatter block: {source_path}")
    try:
        _, block, _ = content.split("---", 2)
    except ValueError as exc:
        raise MetadataError("MISSING_FRONTMATTER", f"Unterminated frontmatter: {source_path}") from exc
    fields: dict[str, str] = {}
    for line in block.strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def validate_source_file(item: PolicySourceMetadata, repo_root: Path = PROJECT_ROOT) -> str:
    """Validate one manifest item against its source file; return file content."""
    source_path = repo_root / item.path
    if not source_path.is_file():
        raise MetadataError("SOURCE_FILE_MISSING", f"Policy source file missing: {source_path}")
    content = source_path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(content, source_path)

    for field_name in ("source_id", "version", "risk_indicator"):
        expected = getattr(item, field_name)
        actual = frontmatter.get(field_name)
        if actual != expected:
            raise MetadataError(
                "FRONTMATTER_MISMATCH",
                f"{source_path}: frontmatter {field_name}={actual!r} "
                f"does not match manifest {expected!r}",
            )
    if item.title not in content:
        raise MetadataError(
            "TITLE_MISMATCH", f"{source_path}: manifest title {item.title!r} not found in content"
        )
    return content


def iter_source_chunks(
    item: PolicySourceMetadata, content: str
) -> list[PolicyChunkMetadata]:
    """Split one validated source into stable per-section chunk records."""
    chunks: list[PolicyChunkMetadata] = []
    # Each ``## `` section (up to the next ``## `` or EOF) is one chunk.
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    matches = list(pattern.finditer(content))
    if not matches:
        raise MetadataError("NO_CHUNKS", f"No '## ' sections found for {item.source_id}")

    for index, match in enumerate(matches, start=1):
        section_heading = match.group(1).strip()
        span_start = match.start()
        span_end = matches[index].start() if index < len(matches) else len(content)
        chunks.append(
            PolicyChunkMetadata(
                source_id=item.source_id,
                version=item.version,
                title=item.title,
                chunk_id=chunk_id_for(item.source_id, index),
                chunk_index=index,
                section_heading=section_heading,
                source_path=item.path,
                char_start=span_start,
                char_end=span_end,
            )
        )
    return chunks


def build_chunk_index(
    manifest_path: Path | str = MANIFEST_PATH, repo_root: Path = PROJECT_ROOT
) -> list[PolicyChunkMetadata]:
    """Validate the full corpus and return every chunk with stable metadata."""
    manifest = load_manifest(manifest_path)
    all_chunks: list[PolicyChunkMetadata] = []
    for item in manifest.items:
        content = validate_source_file(item, repo_root)
        all_chunks.extend(iter_source_chunks(item, content))

    chunk_ids = [c.chunk_id for c in all_chunks]
    duplicates = {cid for cid in chunk_ids if chunk_ids.count(cid) > 1}
    if duplicates:
        raise MetadataError(
            "DUPLICATE_CHUNK_ID", f"Duplicate chunk_id in corpus: {sorted(duplicates)}"
        )
    return all_chunks


def to_evidence_ref(chunk: PolicyChunkMetadata) -> dict[str, str]:
    """Project a chunk record onto the frozen ``PolicyEvidence`` identity fields."""
    return {
        "source_id": chunk.source_id,
        "version": chunk.version,
        "chunk_id": chunk.chunk_id,
    }


__all__ = [
    "CorpusMetadata",
    "MetadataError",
    "PolicyChunkMetadata",
    "PolicySourceMetadata",
    "build_chunk_index",
    "chunk_id_for",
    "iter_source_chunks",
    "load_manifest",
    "parse_frontmatter",
    "to_evidence_ref",
    "validate_source_file",
    "MANIFEST_PATH",
    "SOURCES_DIR",
    "SCHEMA_VERSION",
    "TASK_ID",
]
