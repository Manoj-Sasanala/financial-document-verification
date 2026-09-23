# Provenance (DB-07 v1.0.0)

## Stored provenance record

Every case carries one `provenance` row (`app/db/provenance.py`):

- `processed_at`: ISO-8601 UTC timestamp of the processing run.
- `rule_versions`: deterministic rule versions (e.g. `risk-rules/1.0.0`).
- `model_version`: ML model version that produced the classification.
- `policy_source_versions`: corpus versions backing retrieval evidence.
- `extraction_source_refs`: page and field source references.

## Visibility

`get_case` includes the provenance record under the `provenance` key
(`None` when never recorded), so reviewer UI, QA and case retrieval see
the same traceability metadata the pipeline produced.
