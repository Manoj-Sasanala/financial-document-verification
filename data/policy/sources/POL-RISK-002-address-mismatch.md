---
source_id: POL-RISK-002
version: 1.0.0
risk_indicator: address_mismatch
status: active
scope: MVP synthetic proof-of-address verification
---

# Address mismatch rule

## Purpose

Define the controlled demo rule for a mismatch between the document address and the synthetic reference customer's address.

## Rule

After deterministic normalization, if the document `address` does not match the corresponding reference customer's `address`, the case shall produce the `address_mismatch` risk indicator.

## Evidence

The relevant evidence is the normalized document address and the normalized reference address.

## Expected finding

- Indicator: `address_mismatch`
- Affected field: `address`
- Category: `verification_mismatch`
- Severity: `warning`

## Boundary

This indicator is an attention signal for the MVP. It is not proof of wrongdoing and does not determine the final human decision.

## Source provenance

This is project-authored controlled demo content. No external web or regulatory source is used.