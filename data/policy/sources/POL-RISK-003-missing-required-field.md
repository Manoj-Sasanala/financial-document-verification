---
source_id: POL-RISK-003
version: 1.0.0
risk_indicator: missing_required_field
status: active
scope: MVP synthetic proof-of-address verification
---

# Missing required field rule

## Purpose

Define the controlled demo rule for required document fields that are missing or explicitly unavailable.

## Rule

If a required MVP document field is missing or cannot be reliably extracted, the case shall produce the `missing_required_field` risk indicator for the affected field.

The fixed MVP required fields are:

- `customer_name`
- `address`
- `document_type`
- `document_date`
- `issuer_name`
- `document_number`
- `postal_code`

`customer_id` is a reference input rather than a document-required field.

## Expected finding

- Indicator: `missing_required_field`
- Affected field: the missing required field
- Category: `validation`
- Severity: `warning`

## Boundary

A missing field must not be silently fabricated or treated as successfully verified. This indicator does not determine the final human decision.

## Source provenance

This is project-authored controlled demo content. No external web or regulatory source is used.