# Demo Runbook (DEP-03 v1.0.0)

Three locked presentation cases, each reproducible from the final build.
Validated inputs live in `data/demo/`; `data/demo/fallback/` holds a local
fallback copy for offline demos.

## Case 1 — Clean (consistent)

- Input: `data/demo/clean-proof.pdf` (synthetic proof of address, CUST-0001).
- Flow: POST `/api/v1/cases` with `customer_id=CUST-0001`.
- Expect: status `completed` (or `completed_with_warnings`), zero risk
  indicators, customer name `Aarav Mehta`, then approve via review endpoint.

## Case 2 — Name mismatch (mismatch_detected)

- Input: same clean PDF shape with customer name `Aarav Sharma`
  (text-pipeline equivalent; see `test_demo_case_name_mismatch`).
- Expect: exactly one indicator, `name_mismatch` (RISK-001), comparison
  `customer_name` mismatch with observed and reference values shown.

## Case 3 — Degraded (unreadable + AI outage)

- Input: unreadable OCR text plus forced RAG/LLM failures.
- Expect: controlled `missing`/`unavailable` outcomes, recoverable stage
  errors, deterministic core intact — no crashes, no invented data.

## Fallback

If the service or network is unavailable, present from
`data/demo/fallback/`: byte-identical input copies plus the expected
indicator lists in `artifacts/qa/qa-02.json` and `artifacts/qa/qa-03.json`.
