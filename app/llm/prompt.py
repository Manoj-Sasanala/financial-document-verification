"""LLM-02: Grounded explanation prompt.

Versioned prompt template instructing the LLM to explain a verification
outcome without inventing facts or policy.

Grounding rules baked into every prompt (frozen for LLM-02):
  * Use only the provided structured facts and the cited evidence chunks.
  * Never invent policy rules, chunk IDs, field values or rule IDs.
  * Identify source evidence by ``chunk_id`` for every claim.
  * State uncertainty explicitly when evidence is absent (``no_evidence``).
  * Never restate or contradict deterministic findings; explanation only.

``build_prompt`` renders an ``ExplanationInput`` into ``PromptResult``
(prompt text + version + evidence refs). ``artifacts/llm/prompt-version.json``
pins the template version with a content hash for reproducibility.

Explicit failure states use :class:`PromptError` with a stable ``code``.

Consumer: LLM inference client (LLM-03).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.llm.schemas import ExplanationInput

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROMPT_VERSION_PATH = PROJECT_ROOT / "artifacts" / "llm" / "prompt-version.json"

PROMPT_VERSION = "1.0.0"
TASK_ID = "LLM-02"

SYSTEM_RULES = """\
You explain a document verification outcome. Obey these rules:
1. Use ONLY the structured facts and the evidence chunks provided below.
2. NEVER invent policy rules, chunk IDs, field values, or rule IDs.
3. Identify the source evidence by chunk_id for every claim you make.
4. If evidence status is no_evidence, say so explicitly and do not cite policy.
5. NEVER restate, soften, or contradict the deterministic findings and risk indicators; you explain them only.
"""


class PromptError(ValueError):
    """Controlled prompt failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass(frozen=True)
class PromptResult:
    """Rendered prompt with version and cited evidence refs."""

    prompt_text: str
    prompt_version: str = PROMPT_VERSION
    evidence_refs: list[str] = field(default_factory=list)
    template_hash: str = ""


def _facts_block(payload: ExplanationInput) -> str:
    lines = [f"case {payload.case_id}"]
    for comparison in payload.comparisons:
        lines.append(
            f"comparison {comparison.field_name} {comparison.status} "
            f"observed={comparison.observed_value or '-'} "
            f"reference={comparison.reference_value or '-'}"
        )
    for indicator in payload.indicators:
        lines.append(
            f"indicator {indicator.indicator_code} {indicator.rule_id} "
            f"{indicator.severity} {indicator.reason}"
        )
    if payload.ml_classification is not None:
        lines.append(
            f"ml_classification {payload.ml_classification.classification} "
            f"model={payload.ml_classification.model_version}"
        )
    return "\n".join(lines)


def _evidence_block(payload: ExplanationInput) -> tuple[str, list[str]]:
    evidence = payload.policy_evidence
    if evidence is None or evidence.status == "no_evidence" or not evidence.evidence:
        return "evidence status: no_evidence", []
    chunks: list[str] = []
    refs: list[str] = []
    for item in evidence.evidence:
        refs.append(item.chunk_id)
        chunks.append(f"[{item.chunk_id}] ({item.source_id} v{item.version})\n{item.text or ''}")
    return "evidence status: evidence_found\n" + "\n\n".join(chunks), refs


def build_prompt(payload: ExplanationInput) -> PromptResult:
    """Render the versioned grounded prompt for an explanation input."""
    if not isinstance(payload, ExplanationInput):
        raise PromptError("INVALID_INPUT", "payload must be an ExplanationInput.")
    facts = _facts_block(payload)
    evidence_text, refs = _evidence_block(payload)
    template_hash = hashlib.sha256(SYSTEM_RULES.encode("utf-8")).hexdigest()
    text = (
        f"{SYSTEM_RULES}\nprompt_version: {PROMPT_VERSION}\n\n"
        f"FACTS\n{facts}\n\nEVIDENCE\n{evidence_text}\n\n"
        "Explain the verification outcome for a human reviewer."
    )
    return PromptResult(
        prompt_text=text, prompt_version=PROMPT_VERSION,
        evidence_refs=refs, template_hash=template_hash,
    )


def write_prompt_version(path: Path | str = PROMPT_VERSION_PATH) -> Path:
    """Persist the pinned prompt version metadata."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "task_id": TASK_ID,
        "prompt_version": PROMPT_VERSION,
        "template_sha256": hashlib.sha256(SYSTEM_RULES.encode("utf-8")).hexdigest(),
        "input_schema_version": "1.0.0",
    }
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return out


__all__ = [
    "PromptError",
    "PromptResult",
    "build_prompt",
    "write_prompt_version",
    "PROMPT_VERSION",
    "PROMPT_VERSION_PATH",
    "SYSTEM_RULES",
    "TASK_ID",
]
