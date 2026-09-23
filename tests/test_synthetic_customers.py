import json
from pathlib import Path

CUSTOMERS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "synthetic"
    / "customers.json"
)

REQUIRED_FIELDS = {
    "customer_id",
    "customer_name",
    "address",
    "postal_code",
}


def load_customers():
    with CUSTOMERS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def test_customers_dataset_loads():
    customers = load_customers()
    assert isinstance(customers, list)
    assert customers


def test_customer_ids_are_unique():
    customers = load_customers()
    customer_ids = [customer["customer_id"] for customer in customers]
    assert len(customer_ids) == len(set(customer_ids))


def test_customer_records_have_required_fields_only():
    customers = load_customers()

    for customer in customers:
        assert set(customer.keys()) == REQUIRED_FIELDS


def test_customer_records_have_valid_required_values():
    customers = load_customers()

    for customer in customers:
        for field in REQUIRED_FIELDS:
            assert isinstance(customer[field], str)
            assert customer[field].strip()

        assert 1 <= len(customer["customer_id"]) <= 64
        assert 1 <= len(customer["customer_name"]) <= 200
        assert 1 <= len(customer["address"]) <= 500
        assert 1 <= len(customer["postal_code"]) <= 20


def test_dataset_supports_clean_mismatch_and_unknown_customer_cases():
    customers = load_customers()
    customer_ids = {customer["customer_id"] for customer in customers}

    assert len(customer_ids) >= 3
    assert "CUST-UNKNOWN" not in customer_ids