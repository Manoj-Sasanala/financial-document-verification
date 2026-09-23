# Security Checklist (QA-05 v1.0.0)

All items verified by `tests/integration/test_failures.py` and
`tests/integration/test_secrets.py`.

## File handling

- [x] Oversized uploads rejected with `FILE_TOO_LARGE` (10 MiB default).
- [x] Unsupported types rejected with `UNSUPPORTED_FILE_TYPE` (PDF/PNG/JPG only).
- [x] Signature mismatches rejected with `INVALID_FILE_SIGNATURE`.
- [x] Path traversal filenames sanitized to basenames (no `/` or `\` survives).
- [x] Page-count and empty-file limits enforced with explicit codes.

## Secrets

- [x] API keys load server-side from environment only (`app/core/config.py`).
- [x] `.env` is git-ignored and untracked; `.env.example` carries no values.
- [x] No secret value in the frontend, OpenAPI schema, logs or API responses.
- [x] LLM key travels in the Authorization header only, never in payloads.

## Failure behavior

- [x] RAG/LLM outages degrade to controlled statuses with deterministic
      findings preserved (API-06, QA-04 coverage).
