from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = frozenset({".pdf", ".png", ".jpg", ".jpeg"})

PDF_SIGNATURE = b"%PDF-"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"

DEFAULT_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_PAGES = 10


@dataclass(frozen=True)
class UploadValidationConfig:
    """Limits applied at the document-upload boundary."""

    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    max_pages: int = DEFAULT_MAX_PAGES

    def __post_init__(self) -> None:
        if self.max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes must be greater than zero")

        if self.max_pages <= 0:
            raise ValueError("max_pages must be greater than zero")


@dataclass(frozen=True)
class UploadValidationResult:
    """Safe metadata produced after an upload passes validation."""

    filename: str
    extension: str
    content_type: str | None
    size_bytes: int
    page_count: int | None


class UploadValidationError(ValueError):
    """Controlled validation failure for an uploaded document."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def validate_upload(
    filename: str,
    content: bytes,
    *,
    content_type: str | None = None,
    page_count: int | None = None,
    config: UploadValidationConfig | None = None,
) -> UploadValidationResult:
    """
    Validate an uploaded PDF/image before document processing.

    The function does not perform PDF extraction or OCR.

    `page_count` is supplied by the caller when it has already been
    determined by the repository-selected document/PDF handling layer.
    """

    validation_config = config or UploadValidationConfig()

    if not filename or not filename.strip():
        raise UploadValidationError(
            "EMPTY_FILENAME",
            "Uploaded document must have a filename.",
        )

    normalized_filename = filename.replace("\\", "/")
    extension = Path(normalized_filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise UploadValidationError(
            "UNSUPPORTED_FILE_TYPE",
            "Only PDF, PNG, JPG, and JPEG documents are supported.",
        )

    size_bytes = len(content)

    if size_bytes == 0:
        raise UploadValidationError(
            "EMPTY_FILE",
            "Uploaded document is empty.",
        )

    if size_bytes > validation_config.max_file_size_bytes:
        raise UploadValidationError(
            "FILE_TOO_LARGE",
            "Uploaded document exceeds the configured file-size limit.",
        )

    if page_count is not None:
        if page_count <= 0:
            raise UploadValidationError(
                "INVALID_PAGE_COUNT",
                "Document page count must be greater than zero.",
            )

        if page_count > validation_config.max_pages:
            raise UploadValidationError(
                "PAGE_LIMIT_EXCEEDED",
                "Document exceeds the configured page-count limit.",
            )

    _validate_file_signature(extension, content)

    return UploadValidationResult(
        filename=Path(normalized_filename).name,
        extension=extension,
        content_type=content_type,
        size_bytes=size_bytes,
        page_count=page_count,
    )


def _validate_file_signature(extension: str, content: bytes) -> None:
    """Reject files whose binary signature does not match their extension."""

    if extension == ".pdf":
        if not content.startswith(PDF_SIGNATURE):
            raise UploadValidationError(
                "INVALID_FILE_SIGNATURE",
                "File content does not match the PDF file type.",
            )
        return

    if extension == ".png":
        if not content.startswith(PNG_SIGNATURE):
            raise UploadValidationError(
                "INVALID_FILE_SIGNATURE",
                "File content does not match the PNG file type.",
            )
        return

    if extension in {".jpg", ".jpeg"}:
        if not content.startswith(JPEG_SIGNATURE):
            raise UploadValidationError(
                "INVALID_FILE_SIGNATURE",
                "File content does not match the JPEG file type.",
            )
