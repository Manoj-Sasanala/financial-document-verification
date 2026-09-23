"""VER-03: Customer reference lookup.

Retrieves the synthetic customer record for a document ``customer_id``
(DATA-02 dataset, seeded SQLite) for the reference matcher consumer.

Boundary (deterministic):
  * Known ID → ``ReferenceResult`` with ``code="found"`` and the customer
    record (customer_id / customer_name / address / postal_code).
  * Unknown ID (e.g. ``CUST-9999``) → ``code="not_found"`` with
    ``customer=None`` — a controlled result, never an exception and never an
    invented placeholder record.
  * Empty ID → :class:`ReferenceError` with code ``EMPTY_CUSTOMER_ID``.

Explicit failure states use :class:`ReferenceError` with a stable ``code``.

Consumer: reference matcher (VER-04).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.db.repository import RepositoryError, get_customer_by_id


class ReferenceError(ValueError):
    """Controlled lookup failure with a stable error ``code``."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover
        return f"[{self.code}] {super().__str__()}"


@dataclass(frozen=True)
class ReferenceResult:
    """Lookup outcome: found record or controlled not_found."""

    code: str
    customer: dict[str, Any] | None = None
    provenance: dict[str, str | None] = field(default_factory=dict)

    @property
    def found(self) -> bool:
        return self.code == "found"


def lookup_reference(db_path: str | Path, customer_id: str) -> ReferenceResult:
    """Look up the reference customer for a document customer_id."""
    if not isinstance(customer_id, str) or not customer_id.strip():
        raise ReferenceError("EMPTY_CUSTOMER_ID", "customer_id must be non-empty.")
    try:
        row = get_customer_by_id(db_path, customer_id.strip())
    except RepositoryError as exc:
        raise ReferenceError(exc.code, str(exc)) from exc

    provenance = {
        "task_id": "VER-03",
        "source": "customers",
        "database": Path(db_path).name,
    }
    if row is None:
        return ReferenceResult(code="not_found", customer=None, provenance=provenance)
    return ReferenceResult(
        code="found",
        customer={
            "customer_id": row["customer_id"],
            "customer_name": row["customer_name"],
            "address": row["address"],
            "postal_code": row["postal_code"],
        },
        provenance=provenance,
    )


__all__ = [
    "ReferenceError",
    "ReferenceResult",
    "lookup_reference",
]
