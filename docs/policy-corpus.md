# Controlled Policy Corpus

## Corpus identity

- Corpus ID: `kyc-demo-policy-corpus`
- Corpus version: `1.0.0`
- Status: controlled-demo
- Scope: AI KYC Document Verification & Risk Copilot MVP
- Data domain: synthetic proof-of-address verification
- External policy sources: none

This corpus contains project-authored demo policy/rule material used as evidence for RAG retrieval.

It is not a production compliance policy library and does not represent universal regulatory requirements.

## Authority boundary

The deterministic Python verification layer remains authoritative for validation, comparison, and risk indicators.

RAG retrieves policy/rule evidence from this controlled corpus.

RAG does not calculate, override, or replace deterministic findings.

The human reviewer retains final decision authority.

## Controlled source inventory

| Source ID | Version | Risk indicator | Source |
|---|---|---|---|
| POL-RISK-001 | 1.0.0 | name_mismatch | `data/policy/sources/POL-RISK-001-name-mismatch.md` |
| POL-RISK-002 | 1.0.0 | address_mismatch | `data/policy/sources/POL-RISK-002-address-mismatch.md` |
| POL-RISK-003 | 1.0.0 | missing_required_field | `data/policy/sources/POL-RISK-003-missing-required-field.md` |
| POL-RISK-004 | 1.0.0 | invalid_document_date | `data/policy/sources/POL-RISK-004-invalid-document-date.md` |
| POL-RISK-005 | 1.0.0 | reference_customer_not_found | `data/policy/sources/POL-RISK-005-reference-customer-not-found.md` |
| POL-RISK-006 | 1.0.0 | unsupported_document_type | `data/policy/sources/POL-RISK-006-unsupported-document-type.md` |

## Required indicator coverage

The corpus provides at least one source for every risk indicator defined by the Step 6 MVP requirements:

- `name_mismatch` → `POL-RISK-001`
- `address_mismatch` → `POL-RISK-002`
- `missing_required_field` → `POL-RISK-003`
- `invalid_document_date` → `POL-RISK-004`
- `reference_customer_not_found` → `POL-RISK-005`
- `unsupported_document_type` → `POL-RISK-006`

## Versioning

The manifest is the inventory authority for corpus version and source versions.

Each source has:

- a stable `source_id`
- an explicit `version`
- a declared `risk_indicator`
- a controlled status
- a defined scope

Changes to policy meaning should result in a new source version rather than silently changing the meaning of an existing version.

## Provenance

All sources in this corpus are project-authored synthetic/demo material.

No arbitrary web search, external regulatory webpage, or uncontrolled policy content is included as an authoritative source.

## Limitations

This corpus is intentionally small and designed for the hackathon MVP.

It must not be interpreted as a complete regulatory compliance policy set.

A mismatch or risk indicator is an attention signal and is not, by itself, proof of wrongdoing.