# API Response Contracts

This document records the Pydantic response models defined in
`app/core/contracts.py`.

These models follow the frozen DATA-C03 through DATA-C13 interfaces.

## FieldValue

Represents one extracted document field.

| Field | Type | Required |
|---|---|---|
| raw_value | string or null | No |
| status | present / missing / uncertain | Yes |
| source_page | integer or null | No |
| source_reference | string or null | No |

## ExtractedFields

Fixed proof-of-address fields:

- customer_name
- address
- document_type
- document_date
- issuer_name
- document_number
- postal_code

Each field uses `FieldValue`.

## NormalizedFields

Contains the same fixed fields as `ExtractedFields`.

Each field additionally contains:

```text
normalized_value