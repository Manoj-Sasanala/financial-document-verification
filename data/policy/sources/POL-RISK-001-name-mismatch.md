---
source_id: POL-RISK-001
version: 1.0.0
risk_indicator: name_mismatch
status: active
scope: MVP synthetic proof-of-address verification
---

# Name mismatch rule

## Purpose

Define the controlled demo rule for a mismatch between the document customer name and the synthetic reference customer's name.

## Rule

After deterministic normalization, if the document `customer_name` does not match the corresponding reference customer's `customer_name`, the case shall produce the `name_mismatch` risk indicator.

## Evidence

The relevant evidence is the normalized document customer name and the normalized reference customer name.

## Expected finding

- Indicator: `name_mismatch`
- Affected field: `customer_name`
- Category: `verification_mismatch`
- Severity: `warning`

## Boundary

This indicator is an attention signal for the MVP. It is not proof of wrongdoing and does not determine the final human decision.

## Source provenance

This is project-authored controlled demo content. No external web or regulatory source is used.