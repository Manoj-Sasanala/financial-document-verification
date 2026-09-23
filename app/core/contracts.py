from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_value: str | None = None
    status: Literal["present", "missing", "uncertain"]
    source_page: int | None = None
    source_reference: str | None = None


class ExtractedFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: FieldValue
    address: FieldValue
    document_type: FieldValue
    document_date: FieldValue
    issuer_name: FieldValue
    document_number: FieldValue
    postal_code: FieldValue


class NormalizedFieldValue(FieldValue):
    normalized_value: str | None = None


class NormalizedFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: NormalizedFieldValue
    address: NormalizedFieldValue
    document_type: NormalizedFieldValue
    document_date: NormalizedFieldValue
    issuer_name: NormalizedFieldValue
    document_number: NormalizedFieldValue
    postal_code: NormalizedFieldValue


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str
    code: str
    reason: str
    severity: str


class FieldComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str
    status: Literal["match", "mismatch", "missing", "unavailable"]
    observed_value: str | None = None
    reference_value: str | None = None


class RiskIndicator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicator_code: Literal[
        "name_mismatch",
        "address_mismatch",
        "missing_required_field",
        "invalid_document_date",
        "reference_customer_not_found",
        "unsupported_document_type",
    ]
    rule_id: str
    rule_version: str
    severity: str
    category: str | None = None
    reason: str
    field_name: str | None = None


class MLResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: Literal[
        "consistent",
        "mismatch_detected",
        "insufficient_evidence",
    ]
    model_version: str


class PolicyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    version: str
    chunk_id: str
    text: str | None = None
    reference: str | None = None


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["evidence_found", "no_evidence"]
    evidence: list[PolicyEvidence]


class PolicyEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    version: str
    chunk_id: str


class ExplanationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "unavailable", "failed"]
    explanation: str | None = None
    evidence_refs: list[PolicyEvidenceRef]


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject", "request_information"]
    comment: str | None = None
    reviewed_at: datetime


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processed_at: datetime
    rule_versions: list[str]
    model_version: str | None = None
    policy_source_versions: list[str]
    extraction_source_refs: list[str] | None = None


class StageError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    code: str
    message: str
    recoverable: bool


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    status: Literal[
        "processing",
        "completed",
        "completed_with_warnings",
        "failed",
    ]
    fields: ExtractedFields
    normalized_fields: NormalizedFields
    validation: list[Finding]
    comparisons: list[FieldComparison]
    risk_indicators: list[RiskIndicator]
    ml_classification: MLResult | None = None
    policy_evidence: RetrievalResult | None = None
    explanation: ExplanationResult | None = None
    review: ReviewResult | None = None
    provenance: Provenance
    errors: list[StageError]