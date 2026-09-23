"""VER-06: Score boundary lock.

Runtime contract: deterministic verification outputs (validation findings
and risk indicators) are the authoritative MVP risk outputs. AI/RAG/LLM
signals are advisory only — retrieved policy text or model output can never
mutate deterministic findings.

Enforcement for the orchestrator (API-04 wires these in):
  * :func:`seal_verification` snapshots findings + indicators with a digest.
  * :func:`assert_unchanged` raises :class:`BoundaryError` (``MUTATION_ATTEMPT``)
    when post-AI outputs differ from the sealed snapshot.
  * :func:`attach_advisory` records ML/RAG/LLM signals alongside — never
    inside — the sealed deterministic outputs.
  * No numeric score is produced or required anywhere in this module.

Explicit failure states use :class:`BoundaryError` with a stable ``code``.

Consumer: ML/RAG/LLM modules; API response schema.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.core.contracts import Finding, RiskIndicator

CONTRACT_VERSION = "1.0.0"
TASK_ID = "VER-06"


class BoundaryError(ValueError):
    """Controlled boundary failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass(frozen=True)
class SealedVerification:
    """Immutable snapshot of authoritative deterministic outputs."""

    findings: tuple[dict[str, Any], ...]
    indicators: tuple[dict[str, Any], ...]
    digest: str = ""
    contract_version: str = CONTRACT_VERSION
    advisory: tuple[dict[str, Any], ...] = ()


def _digest(findings: list[Finding], indicators: list[RiskIndicator]) -> str:
    payload = {
        "findings": [f.model_dump() for f in findings],
        "indicators": [i.model_dump() for i in indicators],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def seal_verification(
    findings: list[Finding], indicators: list[RiskIndicator]
) -> SealedVerification:
    """Seal deterministic outputs; returns the immutable snapshot."""
    if not isinstance(findings, list) or not isinstance(indicators, list):
        raise BoundaryError(
            "INVALID_INPUT_TYPE", "findings and indicators must be lists."
        )
    if any(not isinstance(f, Finding) for f in findings):
        raise BoundaryError("INVALID_FINDING", "All findings must be Finding records.")
    if any(not isinstance(i, RiskIndicator) for i in indicators):
        raise BoundaryError(
            "INVALID_INDICATOR", "All indicators must be RiskIndicator records."
        )
    frozen_findings = tuple(f.model_dump() for f in findings)
    frozen_indicators = tuple(i.model_dump() for i in indicators)
    return SealedVerification(
        findings=frozen_findings,
        indicators=frozen_indicators,
        digest=_digest(findings, indicators),
    )


def assert_unchanged(
    sealed: SealedVerification,
    findings: list[Finding],
    indicators: list[RiskIndicator],
) -> None:
    """Raise ``MUTATION_ATTEMPT`` when outputs differ from the sealed snapshot."""
    if not isinstance(sealed, SealedVerification):
        raise BoundaryError("INVALID_SEAL", "sealed must be a SealedVerification.")
    if _digest(findings, indicators) != sealed.digest:
        raise BoundaryError(
            "MUTATION_ATTEMPT",
            "Deterministic findings/indicators were mutated after sealing. "
            "AI/RAG/LLM outputs must remain advisory-only.",
        )


def attach_advisory(
    sealed: SealedVerification,
    *,
    ml_classification: str | None = None,
    policy_refs: list[dict[str, str]] | None = None,
    explanation: str | None = None,
) -> SealedVerification:
    """Record advisory AI signals alongside sealed outputs (never inside)."""
    if not isinstance(sealed, SealedVerification):
        raise BoundaryError("INVALID_SEAL", "sealed must be a SealedVerification.")
    advisory = list(sealed.advisory)
    if ml_classification is not None:
        advisory.append({"kind": "ml_classification", "value": ml_classification})
    for ref in policy_refs or []:
        advisory.append({"kind": "policy_evidence", **ref})
    if explanation is not None:
        advisory.append({"kind": "explanation", "value": explanation})
    merged = SealedVerification(
        findings=sealed.findings,
        indicators=sealed.indicators,
        digest=sealed.digest,
        contract_version=sealed.contract_version,
        advisory=tuple(advisory),
    )
    if merged.digest != sealed.digest:
        raise BoundaryError("MUTATION_ATTEMPT", "Sealing digest changed on advisory attach.")
    return merged


__all__ = [
    "BoundaryError",
    "SealedVerification",
    "assert_unchanged",
    "attach_advisory",
    "seal_verification",
    "CONTRACT_VERSION",
    "TASK_ID",
]
