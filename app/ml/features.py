"""ML-01: ML feature text.

Freezes exactly what text the classifier receives for each case, built from
the VER-04 comparison and VER-05 indicator representation.

Feature schema (v1.0.0, deterministic):
  * Line 1: ``schema <FEATURE_SCHEMA_VERSION>``.
  * One line per compared field, in comparison order:
    ``field <name> <status> <observed> => <reference>``
    (missing values render as ``-``).
  * One line per indicator, in assessment order:
    ``indicator <code> <rule_id> <severity>``.
  * One line per validation finding code, in finding order:
    ``finding <code>``.

Same case always yields byte-identical text; any material case difference
changes the text. No model, vocabulary or randomness lives here.

Explicit failure states use :class:`FeatureError` with a stable ``code``.

Consumer: ML training and inference (ML-02, ML-04).
"""

from __future__ import annotations

from app.core.contracts import FieldComparison, Finding, RiskIndicator

FEATURE_SCHEMA_VERSION = "1.0.0"
TASK_ID = "ML-01"


class FeatureError(ValueError):
    """Controlled feature-building failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


def _render(value: str | None) -> str:
    if value is None or not str(value).strip():
        return "-"
    return " ".join(str(value).split())


def build_feature_text(
    comparisons: list[FieldComparison],
    indicators: list[RiskIndicator],
    findings: list[Finding] | None = None,
) -> str:
    """Build deterministic classifier input text for one case."""
    if not isinstance(comparisons, list) or not comparisons:
        raise FeatureError("EMPTY_COMPARISONS", "comparisons must be a non-empty list.")
    if not isinstance(indicators, list):
        raise FeatureError("INVALID_INPUT_TYPE", "indicators must be a list.")
    if findings is not None and not isinstance(findings, list):
        raise FeatureError("INVALID_INPUT_TYPE", "findings must be a list or None.")
    for comparison in comparisons:
        if not isinstance(comparison, FieldComparison):
            raise FeatureError("INVALID_COMPARISON", "All comparisons must be FieldComparison.")

    lines = [f"schema {FEATURE_SCHEMA_VERSION}"]
    for comparison in comparisons:
        lines.append(
            f"field {comparison.field_name} {comparison.status} "
            f"{_render(comparison.observed_value)} => {_render(comparison.reference_value)}"
        )
    for indicator in indicators:
        if not isinstance(indicator, RiskIndicator):
            raise FeatureError("INVALID_INDICATOR", "All indicators must be RiskIndicator.")
        lines.append(
            f"indicator {indicator.indicator_code} {indicator.rule_id} {indicator.severity}"
        )
    for finding in findings or []:
        if not isinstance(finding, Finding):
            raise FeatureError("INVALID_FINDING", "All findings must be Finding.")
        lines.append(f"finding {finding.code}")
    return "\n".join(lines) + "\n"


__all__ = [
    "FeatureError",
    "build_feature_text",
    "FEATURE_SCHEMA_VERSION",
    "TASK_ID",
]
