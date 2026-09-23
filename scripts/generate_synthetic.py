from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CUSTOMERS_PATH = PROJECT_ROOT / "data" / "synthetic" / "customers.json"
TEMPLATE_PATH = PROJECT_ROOT / "data" / "synthetic" / "documents" / "template.html"

CLEAN_DIR = PROJECT_ROOT / "data" / "synthetic" / "documents" / "clean"
MISMATCH_DIR = PROJECT_ROOT / "data" / "synthetic" / "documents" / "mismatch"

SCENARIOS_PATH = PROJECT_ROOT / "data" / "synthetic" / "scenarios.json"

TEMPLATE_VERSION = "1.0.0"
GENERATOR_VERSION = "1.0.0"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_customers() -> list[dict[str, str]]:
    customers = load_json(CUSTOMERS_PATH)

    if not isinstance(customers, list) or not customers:
        raise ValueError("customers.json must contain a non-empty list")

    return customers


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def render_document(
    template: str,
    customer: dict[str, str],
) -> str:
    replacements = {
        "CUST-0001": customer["customer_id"],
        "Aarav Mehta": customer["customer_name"],
        "42 Example Avenue, Vijayawada": customer["address"],
        "520001": customer["postal_code"],
    }

    rendered = template

    for source, replacement in replacements.items():
        rendered = rendered.replace(source, replacement)

    return rendered


def write_document(
    directory: Path,
    filename: str,
    content: str,
) -> str:
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / filename
    path.write_text(content, encoding="utf-8")

    return path.relative_to(PROJECT_ROOT).as_posix()


def build_scenarios(customer: dict[str, str]) -> list[dict[str, Any]]:
    customer_id = customer["customer_id"]

    clean_observed = {
        "customer_id": customer_id,
        "customer_name": customer["customer_name"],
        "address": customer["address"],
        "postal_code": customer["postal_code"],
    }

    name_mismatch_observed = {
        **clean_observed,
        "customer_name": "Aarav Sharma",
    }

    address_mismatch_observed = {
        **clean_observed,
        "address": "99 Synthetic Street, Vijayawada",
    }

    clean_path = write_document(
        CLEAN_DIR,
        f"{customer_id}-clean.html",
        render_document(TEMPLATE, clean_observed),
    )

    name_path = write_document(
        MISMATCH_DIR,
        f"{customer_id}-name-mismatch.html",
        render_document(TEMPLATE, name_mismatch_observed),
    )

    address_path = write_document(
        MISMATCH_DIR,
        f"{customer_id}-address-mismatch.html",
        render_document(TEMPLATE, address_mismatch_observed),
    )

    return [
        {
            "scenario_id": "DATA-04-CLEAN-001",
            "scenario_type": "clean",
            "customer_id": customer_id,
            "document_path": clean_path,
            "template_version": TEMPLATE_VERSION,
            "generator_version": GENERATOR_VERSION,
            "ground_truth": {
                "expected_outcome": "consistent",
                "mismatch_fields": [],
                "reference": clean_observed,
                "observed": clean_observed,
            },
            "provenance": {
                "source_customer": "data/synthetic/customers.json",
                "source_template": "data/synthetic/documents/template.html",
            },
        },
        {
            "scenario_id": "DATA-04-NAME-001",
            "scenario_type": "name_mismatch",
            "customer_id": customer_id,
            "document_path": name_path,
            "template_version": TEMPLATE_VERSION,
            "generator_version": GENERATOR_VERSION,
            "ground_truth": {
                "expected_outcome": "mismatch_detected",
                "expected_indicator": "name_mismatch",
                "mismatch_fields": ["customer_name"],
                "reference": clean_observed,
                "observed": name_mismatch_observed,
            },
            "provenance": {
                "source_customer": "data/synthetic/customers.json",
                "source_template": "data/synthetic/documents/template.html",
            },
        },
        {
            "scenario_id": "DATA-04-ADDRESS-001",
            "scenario_type": "address_mismatch",
            "customer_id": customer_id,
            "document_path": address_path,
            "template_version": TEMPLATE_VERSION,
            "generator_version": GENERATOR_VERSION,
            "ground_truth": {
                "expected_outcome": "mismatch_detected",
                "expected_indicator": "address_mismatch",
                "mismatch_fields": ["address"],
                "reference": clean_observed,
                "observed": address_mismatch_observed,
            },
            "provenance": {
                "source_customer": "data/synthetic/customers.json",
                "source_template": "data/synthetic/documents/template.html",
            },
        },
    ]


def main() -> None:
    global TEMPLATE

    customers = load_customers()

    selected_customer = next(
        (
            customer
            for customer in customers
            if customer["customer_id"] == "CUST-0001"
        ),
        None,
    )

    if selected_customer is None:
        raise ValueError("Required synthetic customer CUST-0001 was not found")

    TEMPLATE = load_template()

    scenarios = build_scenarios(selected_customer)

    SCENARIOS_PATH.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": "1.0.0",
        "task_id": "DATA-04",
        "generator_version": GENERATOR_VERSION,
        "template_version": TEMPLATE_VERSION,
        "synthetic_only": True,
        "source_customer_file": "data/synthetic/customers.json",
        "source_template": "data/synthetic/documents/template.html",
        "scenarios": scenarios,
    }

    SCENARIOS_PATH.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Generated {len(scenarios)} DATA-04 scenarios.")
    for scenario in scenarios:
        print(
            f"{scenario['scenario_id']}: "
            f"{scenario['document_path']}"
        )

    print(f"Scenario manifest: {SCENARIOS_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()