import json
from pathlib import Path


SCENARIOS_PATH = Path("data/synthetic/scenarios.json")
EDGE_DIR = Path("data/synthetic/documents/edge")
CUSTOMERS_PATH = Path("data/synthetic/customers.json")


def load_scenarios():
    with SCENARIOS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_customers():
    with CUSTOMERS_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_data05_scenarios():
    data = load_scenarios()

    return [
        scenario
        for scenario in data["scenarios"]
        if scenario["scenario_id"].startswith("DATA-05-")
    ]


def test_required_data05_edge_cases_exist():
    scenarios = get_data05_scenarios()

    required_types = {
        "missing_field",
        "invalid_date",
        "unsupported_document",
        "unknown_customer",
        "unreadable_ocr",
    }

    actual_types = {
        scenario["scenario_type"]
        for scenario in scenarios
    }

    assert actual_types == required_types
    assert len(scenarios) == 5


def test_data05_document_paths_exist():
    scenarios = get_data05_scenarios()

    for scenario in scenarios:
        path = Path(scenario["document_path"])

        assert path.exists(), f"Missing artifact: {path}"
        assert path.is_file()
        assert path.parent == EDGE_DIR


def test_data05_scenarios_have_explicit_ground_truth():
    scenarios = get_data05_scenarios()

    for scenario in scenarios:
        ground_truth = scenario["ground_truth"]

        assert "expected_outcome" in ground_truth
        assert "expected_indicator" in ground_truth
        assert "provenance" in scenario

        assert scenario["provenance"]["source_customer"] == (
            "data/synthetic/customers.json"
        )

        assert scenario["provenance"]["source_template"] == (
            "data/synthetic/documents/template.html"
        )


def test_missing_address_case():
    path = EDGE_DIR / "CUST-0001-missing-address.html"

    content = path.read_text(encoding="utf-8")

    assert 'data-field="customer_id"' in content
    assert 'data-field="customer_name"' in content
    assert 'data-field="address"' in content
    assert 'data-field="postal_code"' in content

    address_start = content.index('data-field="address"')
    address_section = content[address_start:]

    assert '<div class="value"></div>' in address_section


def test_invalid_date_case():
    path = EDGE_DIR / "CUST-0001-invalid-date.html"

    content = path.read_text(encoding="utf-8")

    assert 'data-field="document_date"' in content
    assert "2026-02-30" in content


def test_unsupported_document_case():
    path = EDGE_DIR / "CUST-0001-unsupported-document.html"

    content = path.read_text(encoding="utf-8")

    assert "UTILITY SERVICE NOTICE" in content
    assert "unsupported-document" in content
    assert "CUST-0001" in content


def test_unknown_customer_case():
    customers = load_customers()

    assert isinstance(customers, list)

    known_ids = {
        customer["customer_id"]
        for customer in customers
    }

    assert "CUST-9999" not in known_ids

    path = EDGE_DIR / "CUST-9999-unknown-customer.html"

    content = path.read_text(encoding="utf-8")

    assert "CUST-9999" in content
    assert "Synthetic Unknown Customer" in content


def test_unreadable_ocr_case():
    path = EDGE_DIR / "CUST-0001-unreadable-ocr.html"

    content = path.read_text(encoding="utf-8")

    assert "████" in content
    assert "▓▓▓▓" in content
    assert "???" in content
    assert "unreadable/OCR-hostile" in content
    