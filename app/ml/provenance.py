"""ML-05: Model provenance.

Makes predictions traceable to a specific model build: every stored ML
result carries the model version plus SHA-256 hashes of the exact artifact
bytes (vectorizer + classifier) that produced it.

  * :func:`build_provenance` snapshots version, feature schema, training
    metadata and artifact hashes from an artifacts directory.
  * :func:`attach_provenance` binds an ``MLResult`` to its provenance for
    storage (DB-05) and reviewer UI display.
  * :func:`verify_provenance` re-hashes the artifacts and raises when the
    stored record no longer matches the model on disk.

Explicit failure states use :class:`ProvenanceError` with a stable ``code``.

Consumer: SQLite persistence; reviewer UI.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.contracts import MLResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "ml"

TASK_ID = "ML-05"


class ProvenanceError(ValueError):
    """Controlled provenance failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise ProvenanceError("ARTIFACTS_MISSING", f"Artifact missing: {path}") from exc
    except OSError as exc:
        raise ProvenanceError("ARTIFACTS_UNREADABLE", f"Cannot read {path}: {exc}") from exc


def build_provenance(artifacts_dir: Path | str = ARTIFACTS_DIR) -> dict[str, Any]:
    """Snapshot model provenance from an artifacts directory."""
    directory = Path(artifacts_dir)
    metadata_path = directory / "model_metadata.json"
    if not metadata_path.is_file():
        raise ProvenanceError("METADATA_MISSING", f"model_metadata.json not found: {directory}")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProvenanceError("METADATA_INVALID", f"Invalid model_metadata.json: {exc}") from exc
    if not metadata.get("model_version"):
        raise ProvenanceError("VERSION_MISSING", "model_metadata.json has no model_version.")
    return {
        "task_id": TASK_ID,
        "model_version": str(metadata["model_version"]),
        "feature_schema": metadata.get("feature_schema"),
        "model": metadata.get("model"),
        "sklearn_version": metadata.get("sklearn_version"),
        "num_train_examples": metadata.get("num_train_examples"),
        "artifact_hashes": {
            "vectorizer.joblib": _sha256(directory / "vectorizer.joblib"),
            "classifier.joblib": _sha256(directory / "classifier.joblib"),
        },
    }


def attach_provenance(
    result: MLResult, provenance: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Bind an inference result to model provenance for storage/display."""
    if not isinstance(result, MLResult):
        raise ProvenanceError("INVALID_RESULT", "result must be an MLResult.")
    provenance = dict(provenance) if provenance is not None else build_provenance()
    if provenance.get("model_version") != result.model_version:
        raise ProvenanceError(
            "VERSION_MISMATCH",
            f"Provenance version {provenance.get('model_version')!r} does not match "
            f"result version {result.model_version!r}.",
        )
    return {
        "classification": result.classification,
        "model_version": result.model_version,
        "provenance": provenance,
    }


def verify_provenance(
    record: dict[str, Any], artifacts_dir: Path | str = ARTIFACTS_DIR
) -> None:
    """Prove a stored record still matches the model bytes on disk."""
    if not isinstance(record, dict) or "provenance" not in record:
        raise ProvenanceError("INVALID_RECORD", "record must carry provenance.")
    current = build_provenance(artifacts_dir)
    stored_hashes = (record["provenance"] or {}).get("artifact_hashes", {})
    if stored_hashes != current["artifact_hashes"]:
        raise ProvenanceError(
            "PROVENANCE_MISMATCH",
            "Stored artifact hashes differ from the model on disk.",
        )
    if record.get("model_version") != current["model_version"]:
        raise ProvenanceError(
            "VERSION_MISMATCH", "Stored model version differs from disk."
        )


__all__ = [
    "ProvenanceError",
    "attach_provenance",
    "build_provenance",
    "verify_provenance",
    "ARTIFACTS_DIR",
    "TASK_ID",
]
