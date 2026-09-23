"""VER-05: Deterministic risk indicators.

Translates VER-02 validation findings and VER-04 comparisons into explicit
attention signals (frozen ``RiskIndicator`` records).

Rule set (frozen for VER-05, version 1.0.0):
  * RISK-001 name_mismatch (warning, verification_mismatch)
  * RISK-002 address_mismatch (warning, verification_mismatch)
  * RISK-003 missing_required_field (error, completeness)
  * RISK-004 invalid_document_date (error, validity)
  * RISK-005 reference_customer_not_found (error, reference)
  * RISK-006 unsupported_document_type (error, document_scope)

A mismatch or risk indicator is an attention signal, not proof of
wrongdoing. Rules are deterministic: same inputs always yield the same
indicator list in rule order. Supported document types are the normalized
proof-of-address variants; anything else present raises RISK-006.

Explicit failure states use :class:`RiskRuleError` with a stable ``code``.

Consumer: ML case representation; RAG query builder; reviewer UI;
persistence.
"""

from __future__ import annotations

from app.core.contracts import FieldComparison, Finding, RiskIndicator
from app.verification.validate import REQUIRED_FIELDS

RULE_VERSION = "1.0.0"

SUPPORTED_DOCUMENT_TYPES = frozenset(
    {"proof of address", "proof_of_address", "poa", "address proof"}
)


class RiskRuleError(ValueError):
    """Controlled risk-rule failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _indicator(
    code: str,
    rule_id: str,
    severity: str,
    category: str,
    reason: str,
    field_name: str | None = None,
) -> RiskIndicator:
    return RiskIndicator(
        indicator_code=code,  # type: ignore[arg-type]
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        severity=severity,
        category=category,
        reason=reason,
        field_name=field_name,
    )


def assess_risk(
    findings: list[Finding],
    comparisons: list[FieldComparison],
    *,
    reference_found: bool = True,
    document_type: str | None = None,
) -> list[RiskIndicator]:
    """Assess deterministic risk indicators in rule order (RISK-001..006)."""
    if not isinstance(findings, list) or not isinstance(comparisons, list):
        raise RiskRuleError(
            "INVALID_INPUT_TYPE", "findings and comparisons must be lists."
        )

    indicators: list[RiskIndicator] = []
    mismatch_by_field = {c.field_name: c.status for c in comparisons}

    # RISK-001 / RISK-002: comparison mismatches.
    if mismatch_by_field.get("customer_name") == "mismatch":
        indicators.append(
            _indicator(
                "name_mismatch", "RISK-001", "warning", "verification_mismatch",
                "Document customer name differs from the reference customer name.",
                "customer_name",
            )
        )
    if mismatch_by_field.get("address") == "mismatch":
        indicators.append(
            _indicator(
                "address_mismatch", "RISK-002", "warning", "verification_mismatch",
                "Document address differs from the reference customer address.",
                "address",
            )
        )

    # RISK-003 / RISK-004: validation findings. An uncertain required
    # field is also a missing required field: its value cannot be verified.
    for finding in findings:
        if finding.code.startswith("MISSING_") or (
            finding.code.startswith("UNCERTAIN_")
            and finding.field_name in REQUIRED_FIELDS
        ):
            indicators.append(
                _indicator(
                    "missing_required_field", "RISK-003", "error", "completeness",
                    f"Required field '{finding.field_name}' is missing: {finding.reason}",
                    finding.field_name,
                )
            )
        elif finding.code == "INVALID_DOCUMENT_DATE":
            indicators.append(
                _indicator(
                    "invalid_document_date", "RISK-004", "error", "validity",
                    f"Document date is invalid: {finding.reason}",
                    finding.field_name,
                )
            )

    # RISK-005: unknown customer.
    if not reference_found:
        indicators.append(
            _indicator(
                "reference_customer_not_found", "RISK-005", "error", "reference",
                "No reference customer exists for the requested customer_id.",
            )
        )

    # RISK-006: unsupported document type (only when a type was provided).
    if document_type is not None and document_type.strip().lower() not in SUPPORTED_DOCUMENT_TYPES:
        indicators.append(
            _indicator(
                "unsupported_document_type", "RISK-006", "error", "document_scope",
                f"Document type '{document_type}' is not a supported proof of address.",
                "document_type",
            )
        )

    return indicators


def indicator_codes(indicators: list[RiskIndicator]) -> list[str]:
    """Indicator codes in assessment order."""
    return [i.indicator_code for i in indicators]


__all__ = [
    "RiskRuleError",
    "assess_risk",
    "indicator_codes",
    "RULE_VERSION",
    "SUPPORTED_DOCUMENT_TYPES",
]
