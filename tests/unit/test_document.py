import pytest

from app.document.upload_validation import (
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_MAX_PAGES,
    UploadValidationConfig,
    UploadValidationError,
    validate_upload,
)


PDF_BYTES = b"%PDF-1.7\nsynthetic test document"
PNG_BYTES = b"\x89PNG\r\n\x1a\nsynthetic test image"
JPEG_BYTES = b"\xff\xd8\xff\xe0synthetic test image"


def test_valid_pdf_passes_validation():
    result = validate_upload(
        "document.pdf",
        PDF_BYTES,
        content_type="application/pdf",
        page_count=2,
    )

    assert result.filename == "document.pdf"
    assert result.extension == ".pdf"
    assert result.size_bytes == len(PDF_BYTES)
    assert result.page_count == 2


@pytest.mark.parametrize(
    ("filename", "content", "content_type"),
    [
        ("document.png", PNG_BYTES, "image/png"),
        ("document.jpg", JPEG_BYTES, "image/jpeg"),
        ("document.jpeg", JPEG_BYTES, "image/jpeg"),
    ],
)
def test_valid_image_files_pass_validation(filename, content, content_type):
    result = validate_upload(
        filename,
        content,
        content_type=content_type,
    )

    assert result.extension in {".png", ".jpg", ".jpeg"}
    assert result.size_bytes == len(content)


@pytest.mark.parametrize(
    "filename",
    [
        "document.txt",
        "document.docx",
        "document.exe",
        "document.zip",
    ],
)
def test_unsupported_file_type_is_rejected(filename):
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(filename, b"synthetic content")

    assert exc_info.value.code == "UNSUPPORTED_FILE_TYPE"


def test_empty_filename_is_rejected():
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload("", PDF_BYTES)

    assert exc_info.value.code == "EMPTY_FILENAME"


def test_empty_file_is_rejected():
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload("document.pdf", b"")

    assert exc_info.value.code == "EMPTY_FILE"


def test_oversized_file_is_rejected():
    config = UploadValidationConfig(
        max_file_size_bytes=10,
        max_pages=DEFAULT_MAX_PAGES,
    )

    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(
            "document.pdf",
            PDF_BYTES,
            config=config,
        )

    assert exc_info.value.code == "FILE_TOO_LARGE"


def test_page_limit_is_enforced():
    config = UploadValidationConfig(
        max_file_size_bytes=DEFAULT_MAX_FILE_SIZE_BYTES,
        max_pages=2,
    )

    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(
            "document.pdf",
            PDF_BYTES,
            page_count=3,
            config=config,
        )

    assert exc_info.value.code == "PAGE_LIMIT_EXCEEDED"


def test_invalid_page_count_is_rejected():
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(
            "document.pdf",
            PDF_BYTES,
            page_count=0,
        )

    assert exc_info.value.code == "INVALID_PAGE_COUNT"


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("document.pdf", b"not really a pdf"),
        ("document.png", b"not really a png"),
        ("document.jpg", b"not really a jpeg"),
        ("document.jpeg", b"not really a jpeg"),
    ],
)
def test_mismatched_file_signature_is_rejected(filename, content):
    with pytest.raises(UploadValidationError) as exc_info:
        validate_upload(filename, content)

    assert exc_info.value.code == "INVALID_FILE_SIGNATURE"


def test_filename_does_not_expose_full_filesystem_path():
    result = validate_upload(
        "/tmp/private/customer/document.pdf",
        PDF_BYTES,
    )

    assert result.filename == "document.pdf"
    assert "/tmp/private" not in result.filename


def test_windows_filename_does_not_expose_full_filesystem_path():
    result = validate_upload(
        r"C:\private\customer\document.pdf",
        PDF_BYTES,
    )

    assert result.filename == "document.pdf"
    assert "\\" not in result.filename


def test_custom_limits_are_supported():
    config = UploadValidationConfig(
        max_file_size_bytes=100,
        max_pages=3,
    )

    result = validate_upload(
        "document.pdf",
        PDF_BYTES,
        page_count=3,
        config=config,
    )

    assert result.size_bytes == len(PDF_BYTES)
    assert result.page_count == 3
