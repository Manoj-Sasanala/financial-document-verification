---
source_id: POL-RISK-004
version: 1.0.0
risk_indicator: invalid_document_date
status: active
scope: MVP synthetic proof-of-address verification
---

# Invalid document date rule

## Purpose

Define the controlled demo rule for an invalid or unusable `document_date`.

## Rule

If the extracted `document_date` is missing, cannot be parsed into the configured date representation, or fails the deterministic date validation rule, the case shall produce the `invalid_document_date` risk indicator.

## Evidence

The relevant evidence is the raw document date and its normalized/validated representation.

## Expected finding

- Indicator: `invalid_document_date`
- Affected field: `document_date`
- Category: `validation`
- Severity: `warning`

## Boundary

The rule does not infer a date that is not present in the document. This indicator does not determine the final human decision.

## Source provenance

This is project-authored controlled demo content. No external web or regulatory source is used.