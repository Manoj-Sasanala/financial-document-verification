"""LLM-04: Explanation evidence-reference validation.

Validates the LLM-03 response contract before storage or display: every
cited evidence reference must resolve against the RAG-06 retrieval result.

Boundaries (frozen for LLM-04):
  * ``available`` requires non-empty explanation text AND all refs resolving
    to retrieved chunks (matching source_id/version/chunk_id).
  * Unresolvable refs downgrade the result to ``failed`` (never stored as
    available with dangling citations).
  * ``unavailable``/``failed`` inputs pass through as evidence-unavailable
    statuses with their refs preserved for audit.
  * Empty explanation text on an ``available`` result also downgrades to
    ``failed``.

Explicit failure states use :class:`ExplanationValidationError` with a
stable ``code`` for malformed inputs (wrong types only).

Consumer: reviewer UI; persistence (DB-05).
"""

from __future__ import annotations

from app.core.contracts import ExplanationResult, RetrievalResult

TASK_ID = "LLM-04"


class ExplanationValidationError(ValueError):
    """Controlled validation failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def validate_explanation(
    result: ExplanationResult, retrieval: RetrievalResult | None = None
) -> ExplanationResult:
    """Validate an explanation response against retrieved evidence."""
    if not isinstance(result, ExplanationResult):
        raise ExplanationValidationError("INVALID_INPUT_TYPE", "result must be ExplanationResult.")
    if retrieval is not None and not isinstance(retrieval, RetrievalResult):
        raise ExplanationValidationError(
            "INVALID_RETRIEVAL", "retrieval must be RetrievalResult or None."
        )

    if result.status in ("unavailable", "failed"):
        return ExplanationResult(
            status=result.status,  # type: ignore[arg-type]
            explanation=result.explanation,
            evidence_refs=list(result.evidence_refs),
        )

    # status == available from here.
    if not result.explanation or not result.explanation.strip():
        return ExplanationResult(status="failed", explanation=None,
                                 evidence_refs=list(result.evidence_refs))

    known = set()
    if retrieval is not None:
        known = {
            (e.source_id, e.version, e.chunk_id) for e in retrieval.evidence
        }
    else:
        # Without retrieval context only refs already shaped as chunk ids pass.
        known = set()

    resolved = []
    for ref in result.evidence_refs:
        key = (ref.source_id, ref.version, ref.chunk_id)
        if retrieval is None or key in known:
            resolved.append(ref)
        else:
            return ExplanationResult(status="failed", explanation=None,
                                     evidence_refs=list(result.evidence_refs))
    return ExplanationResult(
        status="available", explanation=result.explanation.strip(), evidence_refs=resolved
    )


__all__ = [
    "ExplanationValidationError",
    "validate_explanation",
    "TASK_ID",
]
