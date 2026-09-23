"""RAG-01 verification: policy document metadata.

DoD: Metadata schema is implemented and validated.
Test: Every policy chunk has stable metadata.
"""

import re

import pytest

from app.core.contracts import PolicyEvidence
from app.rag.metadata import (
    CHUNK_ID_PATTERN,
    MetadataError,
    PolicySourceMetadata,
    build_chunk_index,
    chunk_id_for,
    load_manifest,
    to_evidence_ref,
    validate_source_file,
)


def test_manifest_loads_and_validates_against_schema() -> None:
    manifest = load_manifest()
    assert manifest.corpus_id == "kyc-demo-policy-corpus"
    assert manifest.corpus_version == "1.0.0"
    assert manifest.external_sources_allowed is False
    assert len(manifest.items) == 6


def test_manifest_items_carry_source_id_version_title() -> None:
    manifest = load_manifest()
    for item in manifest.items:
        assert re.match(r"^POL-RISK-\d{3}$", item.source_id)
        assert re.match(r"^\d+\.\d+\.\d+$", item.version)
        assert item.title.strip()
        assert item.risk_indicator.strip()


def test_source_files_match_manifest() -> None:
    manifest = load_manifest()
    for item in manifest.items:
        content = validate_source_file(item)
        assert f"source_id: {item.source_id}" in content
        assert f"version: {item.version}" in content


def test_every_policy_chunk_has_stable_metadata() -> None:
    first = build_chunk_index()
    second = build_chunk_index()
    assert first, "expected at least one policy chunk"

    # Deterministic: identical records across runs.
    assert [c.model_dump() for c in first] == [c.model_dump() for c in second]

    chunk_ids = [c.chunk_id for c in first]
    assert len(set(chunk_ids)) == len(chunk_ids), "chunk_id must be unique"

    for chunk in first:
        assert CHUNK_ID_PATTERN.match(chunk.chunk_id)
        assert chunk.chunk_id == chunk_id_for(chunk.source_id, chunk.chunk_index)
        assert chunk.title.strip()
        assert chunk.section_heading.strip()
        assert chunk.char_end > chunk.char_start


def test_every_source_produces_at_least_one_chunk() -> None:
    manifest = load_manifest()
    chunks = build_chunk_index()
    by_source: dict[str, int] = {}
    for chunk in chunks:
        by_source[chunk.source_id] = by_source.get(chunk.source_id, 0) + 1
    for item in manifest.items:
        assert by_source.get(item.source_id, 0) >= 1, item.source_id


def test_chunk_metadata_matches_frozen_evidence_contract() -> None:
    for chunk in build_chunk_index():
        ref = to_evidence_ref(chunk)
        evidence = PolicyEvidence(**ref, text="demo", reference="demo-ref")
        assert evidence.source_id == chunk.source_id
        assert evidence.version == chunk.version
        assert evidence.chunk_id == chunk.chunk_id


def test_invalid_source_id_is_rejected() -> None:
    with pytest.raises(MetadataError) as exc_info:
        chunk_id_for("NOT-A-SOURCE", 1)
    assert exc_info.value.code == "INVALID_SOURCE_ID"


def test_invalid_chunk_index_is_rejected() -> None:
    with pytest.raises(MetadataError) as exc_info:
        chunk_id_for("POL-RISK-001", 0)
    assert exc_info.value.code == "INVALID_CHUNK_INDEX"


def test_invalid_source_metadata_is_rejected() -> None:
    with pytest.raises(Exception):
        PolicySourceMetadata(
            source_id="BAD-ID",
            version="1.0.0",
            title="t",
            path="p",
            risk_indicator="r",
        )


def test_missing_manifest_is_explicit() -> None:
    with pytest.raises(MetadataError) as exc_info:
        load_manifest("data/policy/does-not-exist.json")
    assert exc_info.value.code == "MANIFEST_NOT_FOUND"
