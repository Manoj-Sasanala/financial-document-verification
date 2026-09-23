---
source_id: POL-RISK-006
version: 1.0.0
risk_indicator: unsupported_document_type
status: active
scope: MVP synthetic proof-of-address verification
---

# Unsupported document type rule

## Purpose

Define the controlled demo rule for documents whose declared or extracted type is outside the configured MVP document type.

## Rule

The MVP supports one configured document type: a synthetic proof-of-address document.

If the document type is not the configured MVP proof-of-address type, the case shall produce the `unsupported_document_type` risk indicator.

## Evidence

The relevant evidence is the extracted `document_type` and the configured MVP document-type value.

## Expected finding

- Indicator: `unsupported_document_type`
- Affected field: `document_type`
- Category: `document_validation`
- Severity: `warning`

## Boundary

This MVP does not attempt generic multi-document verification. The indicator does not determine the final human decision.

## Source provenance

This is project-authored controlled demo content. No external web or regulatory source is used.