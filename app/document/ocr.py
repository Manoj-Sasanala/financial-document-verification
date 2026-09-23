"""DOC-03: OCR fallback for scanned/image documents.

Processes scanned or image-only documents that carry no native PDF text
(DOC-02 reports ``requires_ocr=True`` for those inputs).

Contract (frozen Step 9.6; DOC-03 card):
  * Deliverable is **OCR text or an explicit extraction failure** — a
    controlled failure state is an accepted outcome, not a crash.
  * The OCR engine is an EXTERNAL runtime. This module never assumes one is
    installed: callers may inject any engine callable, and when no engine is
    available the fallback returns a controlled ``ENGINE_UNAVAILABLE``
    failure with evidence/provenance metadata.
  * Provenance (input hash, engine identity, timestamps, source refs) is
    preserved on both success and failure for downstream handoff.

Supported inputs (aligned with DOC-01 upload validation):
  PNG (``image/png``) and JPEG (``image/jpeg``) byte streams.

Consumer: field extractor; failure handling (DOC-04, API-06, QA-04).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"

# Engine callable: receives raw image bytes, returns extracted text, or None
# when the engine finds no text. Any exception is wrapped as OCR_FAILED.
OcrEngine = Callable[[bytes], str | None]


class OcrError(ValueError):
    """Controlled OCR failure with a stable error ``code`` and provenance."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provenance: dict[str, str | int | None] | None = None,
    ) -> None:
        self.code = code
        self.provenance: dict[str, str | int | None] = provenance or {}
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass(frozen=True)
class OcrResult:
    """Successful OCR outcome (text may be empty only via explicit failure)."""

    text: str
    engine: str
    char_count: int = 0
    word_count: int = 0
    sha256: str = ""
    extracted_at: str = ""
    provenance: dict[str, str | int | None] = field(default_factory=dict)


def detect_image_kind(content: bytes) -> str | None:
    """Return ``'png'`` / ``'jpeg'`` for supported signatures, else None."""
    if content.startswith(PNG_SIGNATURE):
        return "png"
    if content.startswith(JPEG_SIGNATURE):
        return "jpeg"
    return None


def _base_provenance(
    content: bytes, *, engine: str, filename: str | None = None
) -> dict[str, str | int | None]:
    sha256 = hashlib.sha256(content).hexdigest()
    provenance: dict[str, str | int | None] = {
        "source_sha256": sha256,
        "extraction_method": "ocr",
        "engine": engine,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": len(content),
    }
    if filename:
        provenance["source_filename"] = Path(filename).name
    return provenance


def _default_engine_name(engine: OcrEngine | None) -> str:
    if engine is None:
        return "none"
    return getattr(engine, "__name__", type(engine).__name__)


def run_ocr(
    image_bytes: bytes,
    *,
    engine: OcrEngine | None = None,
    filename: str | None = None,
) -> OcrResult:
    """Run the OCR fallback over PNG/JPEG bytes.

    Args:
        image_bytes: Raw PNG or JPEG content (DOC-01 validated).
        engine: Optional OCR engine callable. When ``None``, a controlled
            ``ENGINE_UNAVAILABLE`` failure is raised (accepted DOC-03 outcome).
        filename: Optional original filename, kept for provenance only.

    Returns:
        :class:`OcrResult` with non-empty text.

    Raises:
        :class:`OcrError` with a stable ``code``:
            * ``EMPTY_INPUT`` – zero-length bytes
            * ``UNSUPPORTED_INPUT`` – not PNG/JPEG content
            * ``ENGINE_UNAVAILABLE`` – no engine injected (controlled failure)
            * ``OCR_FAILED`` – engine raised
            * ``NO_TEXT_FOUND`` – engine returned no usable text
    """
    if not isinstance(image_bytes, (bytes, bytearray)):
        raise OcrError("INVALID_INPUT_TYPE", "image_bytes must be of type bytes.")
    if len(image_bytes) == 0:
        raise OcrError("EMPTY_INPUT", "Image content is empty.")
    if detect_image_kind(bytes(image_bytes)) is None:
        raise OcrError(
            "UNSUPPORTED_INPUT",
            "Only PNG and JPEG image inputs are supported for OCR fallback.",
        )

    content = bytes(image_bytes)
    engine_name = _default_engine_name(engine)
    if engine is None:
        raise OcrError(
            "ENGINE_UNAVAILABLE",
            "No OCR engine is available in this runtime. "
            "Inject an engine callable to enable text extraction.",
            provenance=_base_provenance(content, engine=engine_name, filename=filename),
        )

    try:
        text = engine(content)
    except Exception as exc:
        raise OcrError(
            "OCR_FAILED",
            f"OCR engine failed: {exc}",
            provenance=_base_provenance(content, engine=engine_name, filename=filename),
        ) from exc

    cleaned = (text or "").strip()
    if not cleaned:
        raise OcrError(
            "NO_TEXT_FOUND",
            "OCR engine returned no usable text for this image.",
            provenance=_base_provenance(content, engine=engine_name, filename=filename),
        )

    return OcrResult(
        text=cleaned,
        engine=engine_name,
        char_count=len(cleaned),
        word_count=len(cleaned.split()),
        sha256=hashlib.sha256(content).hexdigest(),
        extracted_at=datetime.now(timezone.utc).isoformat(),
        provenance=_base_provenance(content, engine=engine_name, filename=filename),
    )


def ocr_required_for(native_text: str, *, min_chars: int = 30, min_words: int = 5) -> bool:
    """Return True when native PDF text is insufficient and OCR should run.

    Mirrors the DOC-02 sufficiency boundary so routing stays consistent.
    """
    stripped = (native_text or "").strip()
    if not stripped:
        return True
    if len(stripped) < min_chars:
        return True
    if len(stripped.split()) < min_words:
        return True
    return False


__all__ = [
    "OcrEngine",
    "OcrError",
    "OcrResult",
    "detect_image_kind",
    "ocr_required_for",
    "run_ocr",
]
