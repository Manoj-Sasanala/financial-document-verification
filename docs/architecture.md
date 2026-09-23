# Architecture

## RAG read-only boundary (RAG-07 v1.0.0)

Retrieval is a read-only operation over the controlled policy corpus:

- `app/rag/retriever.py` exposes only query paths (`retrieve`,
  `retrieve_with_boundary`). It has no write path to validation findings,
  comparisons or risk indicators.
- `retrieve_with_boundary` seals VER-05 outputs via the VER-06 boundary
  before retrieval and proves them unchanged afterwards.
- Replacing retrieved evidence (different query, different chunks, or
  `no_evidence`) leaves deterministic verification and risk outputs
  byte-identical. RAG output is advisory evidence for explanations, never
  an override of deterministic findings.
