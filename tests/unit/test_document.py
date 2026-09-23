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


# ---------------------------------------------------------------------------
# DOC-03: OCR fallback (DoD: OCR path works on at least one prepared image
# case; scanned input yields usable text or a controlled failure state)
# ---------------------------------------------------------------------------

from io import BytesIO  # noqa: E402

import pytest as _pytest  # noqa: E402,F401

from app.document.ocr import (  # noqa: E402
    OcrError,
    detect_image_kind,
    ocr_required_for,
    run_ocr,
)


def _make_scanned_png(lines=("PROOF OF ADDRESS", "Aarav Mehta", "520001")) -> bytes:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (480, 200), color="white")
    draw = ImageDraw.Draw(image)
    y = 20
    for line in lines:
        draw.text((20, y), line, fill="black")
        y += 30
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _stub_engine(expected: bytes, text: str):
    def _engine(payload: bytes) -> str | None:
        assert payload == expected
        return text

    _engine.__name__ = "stub_engine"
    return _engine


def test_ocr_detects_supported_image_kinds():
    image = _make_scanned_png()

    assert detect_image_kind(image) == "png"
    assert detect_image_kind(b"\xff\xd8\xff\x00jpeg") == "jpeg"
    assert detect_image_kind(b"%PDF-1.4") is None


def test_ocr_with_stub_engine_returns_text_on_prepared_image():
    image = _make_scanned_png()

    result = run_ocr(
        image,
        engine=_stub_engine(image, "PROOF OF ADDRESS\nAarav Mehta\n520001"),
        filename="scan.png",
    )

    assert "Aarav Mehta" in result.text
    assert "520001" in result.text
    assert result.engine == "stub_engine"
    assert result.char_count == len(result.text)
    assert result.provenance["extraction_method"] == "ocr"
    assert result.provenance["source_filename"] == "scan.png"


def test_ocr_without_engine_is_controlled_failure_with_provenance():
    image = _make_scanned_png()

    with _pytest.raises(OcrError) as exc_info:
        run_ocr(image, filename="scan.png")

    assert exc_info.value.code == "ENGINE_UNAVAILABLE"
    assert exc_info.value.provenance["extraction_method"] == "ocr"
    assert exc_info.value.provenance["source_filename"] == "scan.png"


def test_ocr_rejects_empty_and_unsupported_inputs():
    with _pytest.raises(OcrError) as exc_info:
        run_ocr(b"")
    assert exc_info.value.code == "EMPTY_INPUT"

    with _pytest.raises(OcrError) as exc_info:
        run_ocr(b"%PDF-1.4 native text, not an image")
    assert exc_info.value.code == "UNSUPPORTED_INPUT"


def test_ocr_engine_empty_result_is_controlled_failure():
    image = _make_scanned_png()

    with _pytest.raises(OcrError) as exc_info:
        run_ocr(image, engine=_stub_engine(image, "   "))
    assert exc_info.value.code == "NO_TEXT_FOUND"


def test_ocr_routing_matches_native_text_sufficiency():
    assert ocr_required_for("") is True
    assert ocr_required_for("hi") is True
    assert ocr_required_for("PROOF OF ADDRESS synthetic proof document text here") is False


def test_image_only_pdf_routes_to_ocr_fallback():
    from app.document.pdf_extract import extract_pdf_text

    blank_pdf = _make_blank_pdf_bytes()
    native = extract_pdf_text(blank_pdf)

    assert native.text == ""
    assert native.requires_ocr is True
    assert ocr_required_for(native.text) is True

    scanned = _make_scanned_png()
    with _pytest.raises(OcrError) as exc_info:
        run_ocr(scanned)
    assert exc_info.value.code == "ENGINE_UNAVAILABLE"


def _make_blank_pdf_bytes() -> bytes:
    from io import BytesIO as _BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = _BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# DOC-04: Fixed field parser (DoD: fixed schema, never invents missing fields;
# clean document yields all required fields present)
# ---------------------------------------------------------------------------

from app.document.field_parser import (  # noqa: E402
    FieldParserError,
    parse_fields,
)


def test_clean_document_yields_required_fields():
    from pathlib import Path as _Path

    from app.document.pdf_extract import extract_pdf_text as _extract

    text = _extract(_Path("data/synthetic/documents/template.pdf").read_bytes()).text
    parsed = parse_fields(text)

    assert parsed.fields.customer_name.status == "present"
    assert parsed.fields.customer_name.raw_value == "Aarav Mehta"
    assert parsed.fields.address.status == "present"
    assert parsed.fields.address.raw_value == "42 Example Avenue, Vijayawada"
    assert parsed.fields.postal_code.status == "present"
    assert parsed.fields.postal_code.raw_value == "520001"
    assert parsed.customer_id == "CUST-0001"


def test_absent_fields_are_missing_not_invented():
    parsed = parse_fields("Customer Name\nAarav Mehta\nPostal Code\n520001")

    assert parsed.fields.document_type.status == "missing"
    assert parsed.fields.document_type.raw_value is None
    assert parsed.fields.document_date.status == "missing"
    assert parsed.fields.issuer_name.status == "missing"
    assert parsed.fields.document_number.status == "missing"


def test_empty_label_value_is_uncertain():
    parsed = parse_fields("Customer Name\nAarav Mehta\nAddress\n\nPostal Code\n520001")

    assert parsed.fields.address.status == "uncertain"
    assert parsed.fields.address.raw_value is None


def test_inline_label_form_is_parsed():
    parsed = parse_fields("Customer Name: Maya Rao\nAddress: 17 Sample Street\nPostal Code: 522001")

    assert parsed.fields.customer_name.raw_value == "Maya Rao"
    assert parsed.fields.address.raw_value == "17 Sample Street"
    assert parsed.fields.postal_code.raw_value == "522001"


def test_empty_text_is_explicit_failure():
    with _pytest.raises(FieldParserError) as exc_info:
        parse_fields("   ")
    assert exc_info.value.code == "EMPTY_TEXT"


def test_parser_output_uses_frozen_contract():
    from app.core.contracts import ExtractedFields

    parsed = parse_fields("Customer Name\nAarav Mehta")

    assert isinstance(parsed.fields, ExtractedFields)
    assert set(ExtractedFields.model_fields.keys()) == {
        "customer_name",
        "address",
        "document_type",
        "document_date",
        "issuer_name",
        "document_number",
        "postal_code",
    }


# ---------------------------------------------------------------------------
# DOC-05: Missing/uncertain evidence (DoD: negative-path tests return explicit
# field status; missing fields stay missing/uncertain, never silently filled)
# ---------------------------------------------------------------------------

from app.document.evidence import (  # noqa: E402
    EvidenceError,
    assert_no_silent_fill,
    build_evidence,
)


def test_missing_address_case_stays_uncertain_with_evidence():
    parsed = parse_fields("Customer Name\nAarav Mehta\nAddress\n\nPostal Code\n520001")
    bundle = build_evidence(parsed, doc_sha256="abc123", extraction_method="native_text")

    assert bundle.status_of("address") == "uncertain"
    assert bundle.status_of("customer_name") == "present"
    assert bundle.status_of("document_type") == "missing"
    assert_no_silent_fill(bundle, parsed)
    assert bundle.provenance["doc_sha256"] == "abc123"


def test_unreadable_case_stays_all_missing():
    parsed = parse_fields("████ ▓▓▓▓ ??? unreadable/OCR-hostile ???")
    bundle = build_evidence(parsed)

    assert {f.status for f in bundle.fields} == {"missing"}
    assert all(f.raw_value is None for f in bundle.fields)
    assert_no_silent_fill(bundle, parsed)


def test_invalid_date_text_is_not_altered_by_evidence():
    parsed = parse_fields("Customer Name\nAarav Mehta\nDocument Date\n2026-02-30")
    bundle = build_evidence(parsed)

    assert bundle.status_of("document_date") == "present"
    record = next(f for f in bundle.fields if f.field_name == "document_date")
    assert record.raw_value == "2026-02-30"
    assert_no_silent_fill(bundle, parsed)


def test_evidence_bundle_hash_is_deterministic():
    parsed = parse_fields("Customer Name\nAarav Mehta\nPostal Code\n520001")

    assert build_evidence(parsed).bundle_hash == build_evidence(parsed).bundle_hash


def test_evidence_rejects_non_parser_input():
    with _pytest.raises(EvidenceError) as exc_info:
        build_evidence({"not": "parsed"})  # type: ignore[arg-type]
    assert exc_info.value.code == "INVALID_INPUT_TYPE"


def test_evidence_status_lookup_rejects_unknown_field():
    parsed = parse_fields("Customer Name\nAarav Mehta")
    bundle = build_evidence(parsed)

    with _pytest.raises(EvidenceError) as exc_info:
        bundle.status_of("passport_number")
    assert exc_info.value.code == "UNKNOWN_FIELD"
