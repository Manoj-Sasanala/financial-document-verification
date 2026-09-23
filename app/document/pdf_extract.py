"""Native PDF text extraction for DOC-02.

Extracts text without OCR when a PDF already contains text (native / born-digital
PDF). Uses ``pypdf`` for deterministic, reproducible extraction.

Interface and data contract
---------------------------
Follows the frozen Step 9.6 data contract:

* Produces non-empty, reproducible text for clean synthetic PDFs.
* ``requires_ocr`` is ``False`` when native text is sufficient so downstream
  stages do not invoke OCR unnecessarily.
* Preserves explicit failure states via :class:`PdfExtractionError` with a
  stable ``code``.
* Preserves evidence/provenance metadata (page count, PDF info dict,
  SHA-256 of the source bytes, extraction method, library version).

Dependencies
------------
* DOC-01 (upload validation) – validates file type / signature before extraction.
* DATA-03 (template) – synthetic proof-of-address template used as ground truth.

Consumer
--------
Field extractor – consumes :attr:`PdfExtractionResult.text` and page-level texts.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

try:
    from pypdf import PdfReader
    import pypdf as _pypdf_module
except ImportError as _import_error:  # pragma: no cover
    PdfReader = None  # type: ignore[assignment]
    _pypdf_module = None  # type: ignore[assignment]
    _IMPORT_ERROR = _import_error
else:
    _IMPORT_ERROR = None

# Minimum number of non-whitespace characters that indicates native text is
# sufficient and OCR is not required. The clean synthetic PDF contains ~300+
# characters, so a low threshold preserves the DoD while flagging
# image-only / empty pages as requiring OCR.
MIN_NATIVE_TEXT_CHARS = 30
MIN_NATIVE_WORDS = 5

PDF_SIGNATURE = b"%PDF-"


class PdfExtractionError(ValueError):
    """Controlled extraction failure with a stable error ``code``.

    Attributes:
        code: Machine-readable error code (e.g. ``EMPTY_PDF``).
        message: Human-readable description.
        recoverable: Whether a retry with different params could succeed.
            Native extraction failures for empty/corrupted PDFs are typically
            not recoverable without a new file.
    """

    def __init__(self, code: str, message: str, *, recoverable: bool = False) -> None:
        self.code = code
        self.recoverable = recoverable
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass(frozen=True)
class PdfMetadata:
    """Basic document metadata extracted from the PDF info dict."""

    page_count: int
    pdf_version: str | None = None
    title: str | None = None
    author: str | None = None
    creator: str | None = None
    producer: str | None = None
    subject: str | None = None
    keywords: str | None = None
    creation_date: str | None = None
    modification_date: str | None = None


@dataclass(frozen=True)
class PdfExtractionResult:
    """Result of native PDF text extraction.

    Attributes:
        text: Combined text of all pages (``\\n``-joined page texts).
        page_texts: Per-page extracted text. Empty string for pages with no
            extractable text.
        page_count: Number of pages in the PDF.
        metadata: Basic document metadata (see :class:`PdfMetadata`).
        raw_metadata: Raw PDF info dict as extracted by pypdf (may be empty).
        requires_ocr: ``False`` when native text is sufficient; ``True`` when
            downstream OCR should be considered.
        extraction_method: Always ``\"native_text\"`` for this module.
        sha256: Hex SHA-256 of the source PDF bytes (evidence/provenance).
        char_count: Number of characters in :attr:`text`.
        word_count: Number of whitespace-separated tokens in :attr:`text`.
        extracted_at: ISO-8601 UTC timestamp of extraction (provenance).
        library_version: Version of the PDF library used.
        provenance: Evidence/provenance helper dict for downstream stages.
    """

    text: str
    page_texts: list[str]
    page_count: int
    metadata: PdfMetadata
    raw_metadata: dict[str, str | None]
    requires_ocr: bool
    extraction_method: Literal["native_text"] = "native_text"
    sha256: str = ""
    char_count: int = 0
    word_count: int = 0
    extracted_at: str = ""
    library_version: str | None = None
    provenance: dict[str, str | list[str] | int | None] = field(default_factory=dict)

    def get_evidence_ref(self) -> str:
        """Return a short evidence reference for provenance chains.

        Format: ``sha256:<first-12-hex>:pages:<n>``
        """
        short = self.sha256[:12] if self.sha256 else "unknown"
        return f"sha256:{short}:pages:{self.page_count}"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_pypdf_available() -> None:
    if _IMPORT_ERROR is not None or PdfReader is None:
        raise PdfExtractionError(
            "MISSING_DEPENDENCY",
            "pypdf is required for native PDF extraction but is not installed. "
            "Install with: pip install pypdf",
            recoverable=False,
        )


def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not isinstance(pdf_bytes, (bytes, bytearray)):
        raise PdfExtractionError(
            "INVALID_INPUT_TYPE",
            "pdf_bytes must be of type bytes.",
            recoverable=False,
        )
    if len(pdf_bytes) == 0:
        raise PdfExtractionError(
            "EMPTY_PDF",
            "PDF content is empty.",
            recoverable=False,
        )
    if not pdf_bytes.startswith(PDF_SIGNATURE):
        raise PdfExtractionError(
            "INVALID_PDF_SIGNATURE",
            "File content does not match the PDF file type (missing %PDF- header).",
            recoverable=False,
        )


def _extract_metadata(reader: PdfReader, page_count: int) -> tuple[PdfMetadata, dict[str, str | None]]:
    raw: dict[str, str | None] = {}
    title = author = creator = producer = subject = keywords = creation_date = modification_date = None
    try:
        info = reader.metadata
        if info is not None:
            # pypdf metadata behaves like a dict with attribute access
            for key in list(info.keys()):
                try:
                    raw[str(key)] = str(info[key]) if info[key] is not None else None
                except Exception:
                    raw[str(key)] = None
            title = getattr(info, "title", None) or raw.get("/Title") or raw.get("Title")
            author = getattr(info, "author", None) or raw.get("/Author")
            creator = getattr(info, "creator", None) or raw.get("/Creator")
            producer = getattr(info, "producer", None) or raw.get("/Producer")
            subject = getattr(info, "subject", None) or raw.get("/Subject")
            keywords = raw.get("/Keywords") or raw.get("Keywords")
            creation_date = getattr(info, "creation_date", None)
            if creation_date is not None:
                creation_date = str(creation_date)
            else:
                creation_date = raw.get("/CreationDate")
            modification_date = getattr(info, "modification_date", None)
            if modification_date is not None:
                modification_date = str(modification_date)
            else:
                modification_date = raw.get("/ModDate") or raw.get("/ModificationDate")
    except Exception:
        # Metadata extraction must not fail the whole operation
        pass

    # Try to get PDF version from header or reader
    pdf_version: str | None = None
    try:
        # pypdf exposes pdf_header like "%PDF-1.4"
        header = getattr(reader, "pdf_header", None)
        if header:
            pdf_version = str(header).replace("%PDF-", "").strip()
    except Exception:
        pass

    metadata = PdfMetadata(
        page_count=page_count,
        pdf_version=pdf_version,
        title=title,
        author=author,
        creator=creator,
        producer=producer,
        subject=subject,
        keywords=keywords,
        creation_date=str(creation_date) if creation_date else None,
        modification_date=str(modification_date) if modification_date else None,
    )
    return metadata, raw


def _is_native_text_sufficient(text: str) -> bool:
    """Return True when extracted text is sufficient and OCR is not required."""
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if len(stripped) < MIN_NATIVE_TEXT_CHARS:
        return False
    words = stripped.split()
    if len(words) < MIN_NATIVE_WORDS:
        return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_pdf_text(
    pdf_bytes: bytes,
    *,
    filename: str | None = None,  # accepted for provenance, not required
    min_chars: int = MIN_NATIVE_TEXT_CHARS,
    min_words: int = MIN_NATIVE_WORDS,
) -> PdfExtractionResult:
    """Extract native text from a PDF byte stream.

    Args:
        pdf_bytes: Raw PDF file content.
        filename: Optional original filename for provenance (ignored for
            extraction logic, included in provenance dict when provided).
        min_chars: Override for minimum characters to consider native text
            sufficient.
        min_words: Override for minimum words.

    Returns:
        :class:`PdfExtractionResult` with combined text, per-page texts,
        page count, metadata, and provenance.

    Raises:
        :class:`PdfExtractionError` with a stable ``code``:
            * ``EMPTY_PDF`` – empty bytes
            * ``INVALID_PDF_SIGNATURE`` – missing %PDF- header
            * ``ENCRYPTED_PDF`` – PDF is encrypted and cannot be read
            * ``CORRUPTED_PDF`` – pypdf failed to parse the document
            * ``NO_PAGES`` – PDF contains zero pages
            * ``EXTRACTION_FAILED`` – unexpected extraction error
            * ``MISSING_DEPENDENCY`` – pypdf not installed
    """
    _ensure_pypdf_available()
    _validate_pdf_bytes(pdf_bytes)

    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    extracted_at = datetime.now(timezone.utc).isoformat()
    library_version = getattr(_pypdf_module, "__version__", None) if _pypdf_module else None

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise PdfExtractionError(
            "CORRUPTED_PDF",
            f"Failed to parse PDF: {exc}",
            recoverable=False,
        ) from exc

    # Encrypted PDFs cannot be read without a password
    try:
        if getattr(reader, "is_encrypted", False):
            raise PdfExtractionError(
                "ENCRYPTED_PDF",
                "PDF is encrypted and cannot be extracted without a password.",
                recoverable=False,
            )
    except PdfExtractionError:
        raise
    except Exception as exc:  # pragma: no cover
        raise PdfExtractionError(
            "EXTRACTION_FAILED",
            f"Failed to check encryption status: {exc}",
            recoverable=False,
        ) from exc

    # Page count
    try:
        page_count = len(reader.pages)
    except Exception as exc:
        raise PdfExtractionError(
            "CORRUPTED_PDF",
            f"Failed to determine page count: {exc}",
            recoverable=False,
        ) from exc

    if page_count == 0:
        raise PdfExtractionError(
            "NO_PAGES",
            "PDF contains no pages.",
            recoverable=False,
        )

    metadata, raw_metadata = _extract_metadata(reader, page_count)

    # Extract text per page – each page extraction is isolated so one bad page
    # does not fail the whole document.
    page_texts: list[str] = []
    for idx in range(page_count):
        try:
            page = reader.pages[idx]
            text = page.extract_text()
            # pypdf may return None for image-only pages
            if text is None:
                text = ""
            # Normalize: strip trailing whitespace per page but preserve internal newlines
            # Keep deterministic output – no random ordering.
            page_texts.append(text)
        except Exception as exc:
            # For a single page failure, record empty string and continue.
            # If all pages fail, requires_ocr will be True.
            page_texts.append("")
            # Optionally, could log exc for debugging but not fail.
            _ = exc

    # Combined text – join with newline separator. Preserve page boundaries.
    # Filter: keep page separators even for empty pages so page index is recoverable
    # by downstream consumers via page_texts. For combined text, skip empty pages
    # that would add extra newlines, but keep deterministic joining.
    combined_parts = [t for t in page_texts if t and t.strip()]
    if combined_parts:
        # Use "\n" to join pages; each page text may already contain newlines
        combined_text = "\n".join(combined_parts)
    else:
        # No extractable text at all – return empty string joined
        # (page_texts will contain empty strings, combined is empty)
        combined_text = ""

    # Stable stripping: remove leading/trailing whitespace but preserve internal structure
    # Do not aggressively normalize spaces – keep as extracted for reproducibility
    # However, ensure reproducible result by stripping only outer whitespace
    combined_text = combined_text.strip()

    # Also strip each page text for consistency
    page_texts_stripped = [pt.strip() if pt else "" for pt in page_texts]

    # Determine if OCR is required
    # Allow caller overrides for min_chars/min_words
    if min_chars != MIN_NATIVE_TEXT_CHARS or min_words != MIN_NATIVE_WORDS:
        # Custom threshold check
        stripped = combined_text.strip()
        requires_ocr = not (len(stripped) >= min_chars and len(stripped.split()) >= min_words)
    else:
        requires_ocr = not _is_native_text_sufficient(combined_text)

    char_count = len(combined_text)
    word_count = len(combined_text.split()) if combined_text else 0

    provenance: dict[str, str | list[str] | int | None] = {
        "source_sha256": sha256,
        "extraction_method": "native_text",
        "extracted_at": extracted_at,
        "library_version": library_version,
        "page_count": page_count,
        "requires_ocr": str(requires_ocr),
        "char_count": char_count,
        "word_count": word_count,
    }
    if filename:
        provenance["source_filename"] = Path(filename).name
        provenance["extraction_source_refs"] = [f"{Path(filename).name}#page={i+1}" for i in range(page_count)]
    else:
        provenance["extraction_source_refs"] = [f"pdf#page={i+1}" for i in range(page_count)]

    return PdfExtractionResult(
        text=combined_text,
        page_texts=page_texts_stripped,
        page_count=page_count,
        metadata=metadata,
        raw_metadata=raw_metadata,
        requires_ocr=requires_ocr,
        extraction_method="native_text",
        sha256=sha256,
        char_count=char_count,
        word_count=word_count,
        extracted_at=extracted_at,
        library_version=library_version,
        provenance=provenance,
    )


def extract_text(
    pdf_bytes: bytes,
    *,
    filename: str | None = None,
) -> PdfExtractionResult:
    """Alias for :func:`extract_pdf_text` (consumer-friendly name)."""
    return extract_pdf_text(pdf_bytes, filename=filename)


def extract_native_text(
    pdf_bytes: bytes,
    *,
    filename: str | None = None,
) -> PdfExtractionResult:
    """Alias for :func:`extract_pdf_text` (explicit native-text name)."""
    return extract_pdf_text(pdf_bytes, filename=filename)


def extract_pdf_text_from_path(
    pdf_path: str | Path,
) -> PdfExtractionResult:
    """Extract native text from a PDF file on disk.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        :class:`PdfExtractionResult`.

    Raises:
        :class:`PdfExtractionError` with codes:
            * ``FILE_NOT_FOUND`` – path does not exist
            * plus all codes from :func:`extract_pdf_text`
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise PdfExtractionError(
            "FILE_NOT_FOUND",
            f"PDF file not found: {path}",
            recoverable=False,
        )
    try:
        pdf_bytes = path.read_bytes()
    except Exception as exc:
        raise PdfExtractionError(
            "FILE_READ_ERROR",
            f"Failed to read PDF file {path}: {exc}",
            recoverable=False,
        ) from exc
    return extract_pdf_text(pdf_bytes, filename=path.name)


# Backwards-compat alias for file-path API expected by some consumers
def extract_text_from_path(pdf_path: str | Path) -> PdfExtractionResult:
    """Alias for :func:`extract_pdf_text_from_path`."""
    return extract_pdf_text_from_path(pdf_path)


__all__ = [
    "PdfExtractionError",
    "PdfExtractionResult",
    "PdfMetadata",
    "extract_pdf_text",
    "extract_text",
    "extract_native_text",
    "extract_pdf_text_from_path",
    "extract_text_from_path",
    "MIN_NATIVE_TEXT_CHARS",
    "MIN_NATIVE_WORDS",
]
