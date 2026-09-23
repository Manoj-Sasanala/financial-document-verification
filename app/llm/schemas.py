"""LLM-01: Explanation input schema.

Standardizes exactly what the LLM is allowed to see: structured
verification facts (findings, comparisons, indicators, ML classification)
plus retrieved policy evidence — and nothing else (no raw document text,
no free-form inputs).

Schema (v1.0.0, frozen for LLM-01):
  * ``case_id``: stable case identifier.
  * ``findings``: frozen ``Finding`` records.
  * ``comparisons``: frozen ``FieldComparison`` records.
  * ``indicators``: frozen ``RiskIndicator`` records.
  * ``ml_classification``: frozen ``MLResult`` or None.
  * ``policy_evidence``: frozen ``RetrievalResult`` or None.
  * Extra fields are forbidden; the payload serializes with ``model_dump``.

Explicit failure states use :class:`InputError` with a stable ``code``.

Consumer: LLM client (LLM-02).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.contracts import (
    FieldComparison,
    Finding,
    MLResult,
    RetrievalResult,
    RiskIndicator,
)

SCHEMA_VERSION = "1.0.0"
TASK_ID = "LLM-01"


class InputError(ValueError):
    """Controlled input-building failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


class ExplanationInput(BaseModel):
    """Structured, serializable LLM input (facts + evidence only)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    findings: list[Finding]
    comparisons: list[FieldComparison]
    indicators: list[RiskIndicator]
    ml_classification: MLResult | None = None
    policy_evidence: RetrievalResult | None = None


def build_explanation_input(
    case_id: str,
    findings: list[Finding],
    comparisons: list[FieldComparison],
    indicators: list[RiskIndicator],
    *,
    ml_classification: MLResult | None = None,
    policy_evidence: RetrievalResult | None = None,
) -> ExplanationInput:
    """Assemble and validate the LLM input payload."""
    if not isinstance(case_id, str) or not case_id.strip():
        raise InputError("EMPTY_CASE_ID", "case_id must be a non-empty string.")
    for name, values, kind in (
        ("findings", findings, Finding),
        ("comparisons", comparisons, FieldComparison),
        ("indicators", indicators, RiskIndicator),
    ):
        if not isinstance(values, list):
            raise InputError("INVALID_INPUT_TYPE", f"{name} must be a list.")
        if any(not isinstance(v, kind) for v in values):
            raise InputError("INVALID_RECORD", f"All {name} must be {kind.__name__}.")
    if ml_classification is not None and not isinstance(ml_classification, MLResult):
        raise InputError("INVALID_ML_RESULT", "ml_classification must be MLResult.")
    if policy_evidence is not None and not isinstance(policy_evidence, RetrievalResult):
        raise InputError("INVALID_EVIDENCE", "policy_evidence must be RetrievalResult.")
    try:
        return ExplanationInput(
            case_id=case_id.strip(),
            findings=findings,
            comparisons=comparisons,
            indicators=indicators,
            ml_classification=ml_classification,
            policy_evidence=policy_evidence,
        )
    except Exception as exc:
        raise InputError("SCHEMA_VIOLATION", f"Explanation input invalid: {exc}") from exc


__all__ = [
    "ExplanationInput",
    "InputError",
    "build_explanation_input",
    "SCHEMA_VERSION",
    "TASK_ID",
]
