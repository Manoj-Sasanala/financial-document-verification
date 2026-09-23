# Synthetic Data Scenarios

## DATA-01 — Frozen customer reference schema

The customer reference record is defined by:

`data/synthetic/customers.schema.json`

Schema version:

`1.0.0`

The reference customer contains exactly these fields:

| Field | Required | Type | Purpose |
|---|---|---|---|
| `customer_id` | Yes | string | Stable synthetic lookup identifier |
| `customer_name` | Yes | string | Reference customer name |
| `address` | Yes | string | Reference customer address |
| `postal_code` | Yes | string | Reference postal code |

The schema rejects additional customer properties so downstream components do not silently depend on undeclared fields.

## Reference-data ground truth

The synthetic customer record is the reference truth used for deterministic field comparison.

A customer record is not a verification result. It does not contain:

- document fields
- verification findings
- risk indicators
- ML classifications
- policy evidence
- LLM explanations
- reviewer decisions

Those values belong to downstream processing stages.

## Clean scenario

A clean proof-of-address scenario uses a document whose extracted customer values correspond to the selected reference customer after downstream normalization.

The customer reference record itself does not contain a `scenario` or `match_status` field.

## Mismatch scenarios

Mismatch cases are created by synthetic document inputs, not by changing the customer reference record.

Examples include:

- `customer_name` differs from the reference value.
- `address` differs from the reference value.
- `postal_code` differs from the reference value.

The reference customer remains unchanged so that the expected comparison target is stable and reproducible.

## Missing-field scenarios

A missing customer reference field is not represented as `null` or an invented placeholder.

All four customer reference fields are required by the frozen schema.

Missing document fields are handled by the downstream document extraction/validation stages and are not encoded into the customer reference schema.

## Unknown-customer scenario

An unknown-customer case is not represented by adding a special record to this schema.

It is produced when a requested `customer_id` does not exist in the synthetic customer dataset.

The lookup stage is responsible for returning the controlled `not_found` result.

## Synthetic-only rule

All customer records and document scenarios must contain fake/synthetic information.

No real customer information, credentials, secrets, API keys, or private documents belong in this dataset.

## ML-03 — Held-out evaluation

The TF-IDF + Logistic Regression model (model version `1.0.0`, 9 training
examples) is evaluated exclusively on the held-out set
`data/ml/test.jsonl` (6 examples, 2 per class). The report at
`artifacts/ml/evaluation.json` records the model version, dataset path,
evaluated example IDs and per-label correct/total counts.

Limitation: this is synthetic-only demo data (15 labeled cases total).
Reported metrics describe prototype behavior on controlled fixtures and
must not be interpreted as production classification performance.