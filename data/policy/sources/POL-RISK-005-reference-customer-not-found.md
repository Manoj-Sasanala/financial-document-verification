---
source_id: POL-RISK-005
version: 1.0.0
risk_indicator: reference_customer_not_found
status: active
scope: MVP synthetic proof-of-address verification
---

# Reference customer not found rule

## Purpose

Define the controlled demo rule for a customer reference lookup that does not resolve to a synthetic customer record.

## Rule

If the supplied `customer_id` does not identify a customer in the controlled synthetic reference dataset, the case shall produce the `reference_customer_not_found` risk indicator.

## Evidence

The relevant evidence is the supplied `customer_id` and the result of the deterministic reference lookup.

## Expected finding

- Indicator: `reference_customer_not_found`
- Affected field: `customer_id`
- Category: `reference_validation`
- Severity: `warning`

## Boundary

A failed reference lookup must not be replaced with an invented customer record. The indicator does not determine the final human decision.

## Source provenance

This is project-authored controlled demo content. No external web or regulatory source is used.