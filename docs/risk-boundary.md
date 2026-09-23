# Risk Boundary Contract (VER-06 v1.0.0)

## Authority rule

Deterministic verification outputs — validation findings (VER-02) and risk
indicators (VER-05) — are the authoritative MVP risk outputs.

AI/RAG/LLM signals (ML classification, retrieved policy evidence, generated
explanations) are **advisory only**. Retrieved policy text or model output
must never mutate deterministic findings or indicators.

## No numeric score

No numeric risk score is produced or required. Downstream stages consume the
explicit indicator list; absence of indicators means no attention signal.

## Enforcement

`app/verification/boundary.py` implements the runtime lock for the
orchestrator (API-04 wiring):

- `seal_verification(findings, indicators)` snapshots outputs with a digest.
- `assert_unchanged(sealed, findings, indicators)` raises `MUTATION_ATTEMPT`
  on any post-seal divergence.
- `attach_advisory(...)` records ML/RAG/LLM signals alongside — never
  inside — the sealed outputs.

## Scope

Controlled-demo boundary for the AI KYC Document Verification & Risk Copilot
MVP. A mismatch or risk indicator is an attention signal, not proof of
wrongdoing; the human reviewer retains final decision authority.
