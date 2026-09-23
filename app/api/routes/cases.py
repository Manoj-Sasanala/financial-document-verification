"""API-05: Case lifecycle endpoints.

POST /api/v1/cases — create/analyze a case, return case_id + result payload.
GET /api/v1/cases/{case_id} — retrieve the stored case/result (no recompute).
POST /api/v1/cases/{case_id}/review — persist a human decision.

All responses use frozen schemas. Retrieval rebuilds the stored ``CaseResult``
from persisted rows without invoking models. Failures are explicit HTTP
errors (400 validation, 404 unknown case, 422 bad payload).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.contracts import CaseResult
from app.db.init_db import DEFAULT_DB_PATH, initialize_database

router = APIRouter()


class ReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "request_information"]
    comment: str | None = None


def _db_path() -> Path:
    return Path(os.environ.get("CASE_DB_PATH", str(DEFAULT_DB_PATH)))


def _page_count(pdf_bytes: bytes) -> int | None:
    try:
        from pypdf import PdfReader
        import io as _io

        return len(PdfReader(_io.BytesIO(pdf_bytes)).pages)
    except Exception:
        return None


def _run_analysis(db_path: Path, case_id: str, content: bytes) -> CaseResult:
    from app.db.repository import save_ai_result, save_extracted_fields, save_findings
    from app.document.field_parser import parse_fields
    from app.document.pdf_extract import extract_pdf_text
    from app.orchestration.pipeline import process_case
    from app.verification.normalize import normalize_fields

    native = extract_pdf_text(content)
    parsed = parse_fields(native.text)
    normalized = normalize_fields(parsed.fields)
    save_extracted_fields(db_path, case_id, normalized)

    result = process_case(case_id, db_path=db_path)

    save_findings(
        db_path, case_id,
        findings=result.validation,
        comparisons=result.comparisons,
        indicators=result.risk_indicators,
    )
    evidence_refs = [
        {"source_id": r.source_id, "version": r.version, "chunk_id": r.chunk_id}
        for r in (result.policy_evidence.evidence if result.policy_evidence else [])
    ]
    save_ai_result(
        db_path, case_id,
        ml_classification=result.ml_classification.classification if result.ml_classification else "insufficient_evidence",
        model_version=result.ml_classification.model_version if result.ml_classification else "unknown",
        retrieval_status=result.policy_evidence.status if result.policy_evidence else "no_evidence",
        evidence_refs=evidence_refs,
        explanation_status=result.explanation.status if result.explanation else "unavailable",
        explanation_text=result.explanation.explanation if result.explanation else None,
    )
    return result


@router.post("/api/v1/cases", response_model=CaseResult, status_code=201)
async def create_case(
    customer_id: str = Form(...),
    file: UploadFile = File(...),
) -> CaseResult:
    """Upload a document, analyze it, and return the case result."""
    from app.db.repository import RepositoryError, create_case as _create
    from app.document.upload_validation import UploadValidationError, validate_upload

    content = await file.read()
    filename = file.filename or "upload"
    try:
        validated = validate_upload(
            filename, content,
            content_type=file.content_type, page_count=_page_count(content),
        )
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=f"{exc.code}: {exc}") from exc

    db_path = _db_path()
    initialize_database(db_path)
    case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
    try:
        _create(db_path, case_id, customer_id, validated.filename,
                validated.content_type or "application/octet-stream")
    except RepositoryError as exc:
        raise HTTPException(status_code=400 if exc.code == "CUSTOMER_NOT_FOUND" else 500,
                            detail=f"{exc.code}: {exc}") from exc
    try:
        result = _run_analysis(db_path, case_id, content)
    except HTTPException:
        raise
    except Exception as exc:
        code = getattr(exc, "code", "ANALYSIS_FAILED")
        raise HTTPException(status_code=500, detail=f"{code}: {exc}") from exc

    from app.db.repository import update_case_status

    try:
        update_case_status(db_path, case_id, result.status)
    except RepositoryError:
        pass
    result_dict = result.model_dump()
    result_dict["case_id"] = case_id
    return CaseResult.model_validate(result_dict)


@router.get("/api/v1/cases/{case_id}", response_model=CaseResult)
def get_case(case_id: str) -> CaseResult:
    """Retrieve a stored case/result without recomputation."""
    from app.core.contracts import (
        ExtractedFields,
        FieldComparison,
        FieldValue,
        Finding,
        NormalizedFields,
        NormalizedFieldValue,
        Provenance,
        ReviewResult,
        RiskIndicator,
    )
    from app.db.repository import RepositoryError, get_case as _get
    from datetime import datetime, timezone

    db_path = _db_path()
    try:
        stored = _get(db_path, case_id)
    except RepositoryError as exc:
        raise HTTPException(status_code=404, detail=f"{exc.code}: {exc}") from exc

    def _fv(row: dict, normalized: bool):
        cls = NormalizedFieldValue if normalized else FieldValue
        key = "normalized_value" if normalized else "raw_value"
        return cls(
            raw_value=row.get("raw_value"), status=row.get("status", "missing"),
            source_page=row.get("source_page"), source_reference=row.get("source_reference"),
            **({"normalized_value": row.get(key)} if normalized else {}),
        )

    rows = stored.get("extracted_fields", {})
    fields = ExtractedFields(**{n: _fv(rows.get(n, {}), False) for n in ExtractedFields.model_fields})
    normalized = NormalizedFields(**{n: _fv(rows.get(n, {}), True) for n in NormalizedFields.model_fields})
    findings = [Finding(**{k: r[k] for k in ("field_name", "code", "reason", "severity")})
                for r in stored.get("findings", []) if r.get("kind") == "finding"]
    comparisons = [FieldComparison(field_name=r["ref"], status=r["code"],
                                   observed_value=r.get("observed_value"),
                                   reference_value=r.get("reference_value"))
                   for r in stored.get("findings", []) if r.get("kind") == "comparison"]
    indicators = [RiskIndicator(indicator_code=r["code"], rule_id=r.get("rule_id") or "RISK-000",
                                rule_version=r.get("rule_version") or "1.0.0",
                                severity=r.get("severity") or "warning",
                                category=r.get("category"), reason=r.get("reason") or "",
                                field_name=r["ref"] if r["ref"] != r["code"] else None)
                  for r in stored.get("findings", []) if r.get("kind") == "indicator"]
    ai = stored.get("ai_result") or {}
    from app.core.contracts import MLResult, RetrievalResult

    ml = None
    if ai.get("ml_classification"):
        ml = MLResult(classification=ai["ml_classification"], model_version=ai.get("model_version") or "unknown")
    from app.core.contracts import ExplanationResult, PolicyEvidenceRef

    review = None
    if stored.get("review_decision"):
        review = ReviewResult(decision=stored["review_decision"], comment=stored.get("review_comment"),
                              reviewed_at=datetime.now(timezone.utc))
    status = stored.get("status", "processing")
    errors: list = []
    return CaseResult(
        case_id=case_id, status=status, fields=fields, normalized_fields=normalized,
        validation=findings, comparisons=comparisons, risk_indicators=indicators,
        ml_classification=ml,
        policy_evidence=RetrievalResult(
            status=ai.get("retrieval_status", "no_evidence"),
            evidence=[],
        ) if ai else None,
        explanation=ExplanationResult(
            status=ai.get("explanation_status", "unavailable"),
            explanation=ai.get("explanation_text"),
            evidence_refs=[PolicyEvidenceRef(**r) for r in (ai.get("evidence_refs") or [])],
        ) if ai else None,
        review=review,
        provenance=Provenance(processed_at=datetime.now(timezone.utc), rule_versions=[],
                              policy_source_versions=[]),
        errors=errors,
    )


@router.post("/api/v1/cases/{case_id}/review")
def review_case(case_id: str, request: ReviewRequest) -> dict:
    """Persist a human decision for a case."""
    from app.db.repository import RepositoryError, save_review

    db_path = _db_path()
    try:
        save_review(db_path, case_id, request.decision, request.comment)
    except RepositoryError as exc:
        status_code = 404 if exc.code == "CASE_NOT_FOUND" else 400
        raise HTTPException(status_code=status_code, detail=f"{exc.code}: {exc}") from exc
    return {"case_id": case_id, "decision": request.decision, "comment": request.comment}


__all__ = ["router"]
