"""API-04: Verification orchestrator shell.

Single ordered pipeline function (ORCH-C1 ``process_case``) that wires the
frozen module contracts without duplicating business logic:

  1. Load the case + stored extracted fields (DB-06 repository).
  2. Validate fields (VER-02).
  3. Look up the reference customer (VER-03) and compare (VER-04).
  4. Assess risk indicators (VER-05) and seal outputs (VER-06 boundary).
  5. ML classification (ML-04 inference; model injected or loaded once).
  6. RAG query (RAG-05) + retrieval (RAG-06, boundary-enforced).
  7. LLM prompt (LLM-02) + explanation (LLM-03, optional transport) +
     validation (LLM-04).
  8. Assemble the frozen ``CaseResult`` with provenance and ``StageError``
     entries for any failed stage.

Downstream stages are injectable (``ml_predict``, ``retriever``,
``llm_explain``) so tests run with mocked modules. Stage failures are
recorded as recoverable errors instead of raising, except for a missing
case or unreadable fields which fail the run.

Consumer: verification endpoint (API-05).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.core.contracts import (
    CaseResult,
    ExtractedFields,
    FieldComparison,
    Finding,
    MLResult,
    NormalizedFields,
    Provenance,
    ReviewResult,
    RiskIndicator,
    RetrievalResult,
    StageError,
)

TASK_ID = "API-04"


class PipelineError(ValueError):
    """Controlled orchestrator failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _error(stage: str, code: str, message: str, *, recoverable: bool) -> StageError:
    return StageError(stage=stage, code=code, message=message, recoverable=recoverable)


def _stored_to_normalized(stored: dict[str, dict[str, Any]]) -> NormalizedFields:
    from app.core.contracts import NormalizedFieldValue

    values = {}
    for name in ExtractedFields.model_fields:
        row = stored.get(name, {})
        values[name] = NormalizedFieldValue(
            raw_value=row.get("raw_value"),
            status=row.get("status", "missing"),  # type: ignore[arg-type]
            source_page=row.get("source_page"),
            source_reference=row.get("source_reference"),
            normalized_value=row.get("normalized_value"),
        )
    return NormalizedFields(**values)


def process_case(
    case_id: str,
    *,
    db_path: str | Path,
    ml_model=None,
    retrieval_context: dict[str, Any] | None = None,
    llm_transport=None,
    ml_predict: Callable | None = None,
    retriever: Callable | None = None,
    llm_explain: Callable | None = None,
) -> CaseResult:
    """Run the ordered verification pipeline for one stored case."""
    from app.db.repository import get_case
    from app.verification.boundary import seal_verification
    from app.verification.compare import compare_fields
    from app.verification.reference import lookup_reference
    from app.verification.risk_rules import assess_risk
    from app.verification.validate import validate_fields

    errors: list[StageError] = []
    try:
        case = get_case(db_path, case_id)
    except Exception as exc:
        raise PipelineError(
            getattr(exc, "code", "CASE_UNAVAILABLE"), f"Cannot load case: {exc}"
        ) from exc

    try:
        normalized = _stored_to_normalized(case.get("extracted_fields", {}))
    except Exception as exc:
        raise PipelineError("FIELDS_UNREADABLE", f"Stored fields unreadable: {exc}") from exc

    findings: list[Finding] = validate_fields(normalized)

    customer_id = case.get("customer_id", "")
    try:
        reference = lookup_reference(db_path, customer_id)
    except Exception as exc:
        reference = None
        errors.append(_error("reference", getattr(exc, "code", "REFERENCE_FAILED"),
                             f"Reference lookup failed: {exc}", recoverable=False))

    if reference is None:
        comparisons: list[FieldComparison] = compare_fields(
            normalized, None
        )
        reference_found = False
    else:
        comparisons = compare_fields(
            normalized, reference.customer if reference.found else None
        )
        reference_found = reference.found

    indicators: list[RiskIndicator] = assess_risk(
        findings, comparisons, reference_found=reference_found
    )
    sealed = seal_verification(findings, indicators)

    # ML stage (injectable).
    ml_result: MLResult | None = None
    try:
        if ml_predict is not None:
            ml_result = ml_predict(comparisons, indicators, findings)
        else:
            from app.ml.inference import predict_case

            ml_result = predict_case(comparisons, indicators, findings, ml_model)
    except Exception as exc:
        errors.append(_error("ml", getattr(exc, "code", "ML_FAILED"),
                             f"ML classification failed: {exc}", recoverable=True))
        ml_result = None

    # RAG stages (injectable retriever).
    policy_evidence: RetrievalResult | None = None
    try:
        from app.rag.query_builder import build_query

        query = build_query(indicators, comparisons)
        if retriever is not None:
            policy_evidence = retriever(query)
        else:
            from app.rag.retriever import retrieve_with_boundary

            _, policy_evidence = retrieve_with_boundary(
                query, findings, indicators, context=retrieval_context
            )
    except Exception as exc:
        errors.append(_error("retrieval", getattr(exc, "code", "RETRIEVAL_FAILED"),
                             f"Policy retrieval failed: {exc}", recoverable=True))
        policy_evidence = None

    # LLM stages (injectable explainer).
    explanation = None
    try:
        from app.llm.prompt import build_prompt
        from app.llm.validator import validate_explanation

        if llm_explain is not None:
            explanation = llm_explain(findings, comparisons, indicators,
                                      ml_result, policy_evidence)
        else:
            from app.llm.client import explain
            from app.llm.schemas import build_explanation_input

            payload = build_explanation_input(
                case_id, findings, comparisons, indicators,
                ml_classification=ml_result, policy_evidence=policy_evidence,
            )
            prompt = build_prompt(payload)
            raw = explain(prompt, transport=llm_transport)
            explanation = validate_explanation(raw, policy_evidence)
    except Exception as exc:
        errors.append(_error("explanation", getattr(exc, "code", "EXPLANATION_FAILED"),
                             f"Explanation failed: {exc}", recoverable=True))
        explanation = None

    fatal = [e for e in errors if not e.recoverable]
    has_warnings = any(f.severity != "error" for f in findings) or bool(
        [e for e in errors if e.recoverable]
    )
    if fatal:
        status = "failed"
    elif has_warnings or any(i.severity == "warning" for i in indicators):
        status = "completed_with_warnings"
    else:
        status = "completed"

    review = None
    if case.get("review_decision"):
        review = ReviewResult(
            decision=case["review_decision"],  # type: ignore[arg-type]
            comment=case.get("review_comment"),
            reviewed_at=datetime.now(timezone.utc),
        )

    try:
        from app.rag.metadata import load_manifest

        policy_versions = [load_manifest().corpus_version]
    except Exception:
        policy_versions = []

    provenance = Provenance(
        processed_at=datetime.now(timezone.utc),
        rule_versions=["risk-rules/1.0.0", "boundary/1.0.0"],
        model_version=ml_result.model_version if ml_result else None,
        policy_source_versions=policy_versions,
        extraction_source_refs=None,
    )

    return CaseResult(
        case_id=case_id,
        status=status,  # type: ignore[arg-type]
        fields=_denormalize(normalized),
        normalized_fields=normalized,
        validation=findings,
        comparisons=comparisons,
        risk_indicators=indicators,
        ml_classification=ml_result,
        policy_evidence=policy_evidence,
        explanation=explanation,
        review=review,
        provenance=provenance,
        errors=errors,
    )


def _denormalize(normalized: NormalizedFields) -> ExtractedFields:
    from app.core.contracts import FieldValue

    return ExtractedFields(**{
        name: FieldValue(
            raw_value=getattr(normalized, name).raw_value,
            status=getattr(normalized, name).status,  # type: ignore[arg-type]
            source_page=getattr(normalized, name).source_page,
            source_reference=getattr(normalized, name).source_reference,
        )
        for name in ExtractedFields.model_fields
    })


__all__ = ["PipelineError", "process_case", "TASK_ID"]
