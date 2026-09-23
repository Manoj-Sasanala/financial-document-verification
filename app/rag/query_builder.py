"""RAG-05: Case-to-query builder.

Creates retrieval queries from structured verification findings — never
arbitrary web search. Queries address only the controlled DATA-07 policy
corpus (``kyc-demo-policy-corpus``).

Query shape (deterministic, frozen for RAG-05):
  * Header line: ``corpus kyc-demo-policy-corpus``.
  * One line per indicator, in assessment order:
    ``indicator <code> field <field-or-none>``.
  * One line per mismatched comparison field:
    ``mismatch <field_name>``.
  * Cases with no indicators yield the baseline line:
    ``baseline proof-of-address verification policy``.

Same findings always yield byte-identical query text.

Explicit failure states use :class:`QueryError` with a stable ``code``.

Consumer: runtime retriever (RAG-06).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.contracts import FieldComparison, RiskIndicator

CORPUS_ID = "kyc-demo-policy-corpus"
TASK_ID = "RAG-05"


class QueryError(ValueError):
    """Controlled query-building failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass(frozen=True)
class RetrievalQuery:
    """Deterministic retrieval query for one verification outcome."""

    query_text: str
    indicator_codes: list[str] = field(default_factory=list)
    mismatch_fields: list[str] = field(default_factory=list)
    provenance: dict[str, str | None] = field(default_factory=dict)


def build_query(
    indicators: list[RiskIndicator],
    comparisons: list[FieldComparison],
) -> RetrievalQuery:
    """Build the retrieval query from indicators and comparisons."""
    if not isinstance(indicators, list) or not isinstance(comparisons, list):
        raise QueryError("INVALID_INPUT_TYPE", "indicators and comparisons must be lists.")
    if not comparisons:
        raise QueryError("EMPTY_COMPARISONS", "comparisons must be a non-empty list.")
    for indicator in indicators:
        if not isinstance(indicator, RiskIndicator):
            raise QueryError("INVALID_INDICATOR", "All indicators must be RiskIndicator.")
    for comparison in comparisons:
        if not isinstance(comparison, FieldComparison):
            raise QueryError("INVALID_COMPARISON", "All comparisons must be FieldComparison.")

    lines = [f"corpus {CORPUS_ID}"]
    codes: list[str] = []
    for indicator in indicators:
        field_name = indicator.field_name or "none"
        lines.append(f"indicator {indicator.indicator_code} field {field_name}")
        codes.append(indicator.indicator_code)
    mismatches = [c.field_name for c in comparisons if c.status == "mismatch"]
    for name in mismatches:
        lines.append(f"mismatch {name}")
    if not indicators:
        lines.append("baseline proof-of-address verification policy")

    return RetrievalQuery(
        query_text="\n".join(lines) + "\n",
        indicator_codes=codes,
        mismatch_fields=mismatches,
        provenance={"task_id": TASK_ID, "corpus_id": CORPUS_ID},
    )


__all__ = [
    "QueryError",
    "RetrievalQuery",
    "build_query",
    "CORPUS_ID",
    "TASK_ID",
]
