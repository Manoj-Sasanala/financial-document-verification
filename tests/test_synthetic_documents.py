import json
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CUSTOMERS_PATH = PROJECT_ROOT / "data" / "synthetic" / "customers.json"
TEMPLATE_PATH = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "documents"
    / "template.html"
)
SCENARIOS_PATH = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "scenarios.json"
)

CLEAN_DIR = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "documents"
    / "clean"
)

MISMATCH_DIR = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "documents"
    / "mismatch"
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


class TestSyntheticDocuments(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.customers = load_json(CUSTOMERS_PATH)
        cls.scenarios = load_json(SCENARIOS_PATH)

    def test_scenario_manifest_exists(self) -> None:
        self.assertTrue(SCENARIOS_PATH.is_file())

    def test_manifest_is_for_data_04(self) -> None:
        self.assertEqual(self.scenarios["task_id"], "DATA-04")

    def test_manifest_declares_synthetic_only(self) -> None:
        self.assertTrue(self.scenarios["synthetic_only"])

    def test_required_scenario_types_are_present(self) -> None:
        scenario_types = {
            scenario["scenario_type"]
            for scenario in self.scenarios["scenarios"]
        }

        self.assertIn("clean", scenario_types)
        self.assertIn("name_mismatch", scenario_types)
        self.assertIn("address_mismatch", scenario_types)

    def test_each_scenario_has_a_document(self) -> None:
        for scenario in self.scenarios["scenarios"]:
            document_path = PROJECT_ROOT / scenario["document_path"]

            self.assertTrue(
                document_path.is_file(),
                msg=f"Missing document: {document_path}",
            )

    def test_clean_case_matches_reference_customer(self) -> None:
        scenario = next(
            item
            for item in self.scenarios["scenarios"]
            if item["scenario_type"] == "clean"
        )

        ground_truth = scenario["ground_truth"]

        self.assertEqual(
            ground_truth["reference"],
            ground_truth["observed"],
        )

        self.assertEqual(
            ground_truth["mismatch_fields"],
            [],
        )

        self.assertEqual(
            ground_truth["expected_outcome"],
            "consistent",
        )

    def test_name_mismatch_changes_only_name(self) -> None:
        scenario = next(
            item
            for item in self.scenarios["scenarios"]
            if item["scenario_type"] == "name_mismatch"
        )

        ground_truth = scenario["ground_truth"]

        self.assertEqual(
            ground_truth["expected_indicator"],
            "name_mismatch",
        )

        self.assertEqual(
            ground_truth["mismatch_fields"],
            ["customer_name"],
        )

        self.assertNotEqual(
            ground_truth["reference"]["customer_name"],
            ground_truth["observed"]["customer_name"],
        )

        self.assertEqual(
            ground_truth["reference"]["address"],
            ground_truth["observed"]["address"],
        )

        self.assertEqual(
            ground_truth["reference"]["postal_code"],
            ground_truth["observed"]["postal_code"],
        )

    def test_address_mismatch_changes_only_address(self) -> None:
        scenario = next(
            item
            for item in self.scenarios["scenarios"]
            if item["scenario_type"] == "address_mismatch"
        )

        ground_truth = scenario["ground_truth"]

        self.assertEqual(
            ground_truth["expected_indicator"],
            "address_mismatch",
        )

        self.assertEqual(
            ground_truth["mismatch_fields"],
            ["address"],
        )

        self.assertNotEqual(
            ground_truth["reference"]["address"],
            ground_truth["observed"]["address"],
        )

        self.assertEqual(
            ground_truth["reference"]["customer_name"],
            ground_truth["observed"]["customer_name"],
        )

        self.assertEqual(
            ground_truth["reference"]["postal_code"],
            ground_truth["observed"]["postal_code"],
        )

    def test_document_contains_required_template_fields(self) -> None:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")

        required_fields = [
            "Customer ID",
            "Customer Name",
            "Address",
            "Postal Code",
        ]

        for field in required_fields:
            self.assertIn(field, template)

        for scenario in self.scenarios["scenarios"]:
            document = (
                PROJECT_ROOT / scenario["document_path"]
            ).read_text(encoding="utf-8")

            for field in required_fields:
                self.assertIn(field, document)

    def test_documents_contain_no_real_customer_data(self) -> None:
        customer_names = {
            customer["customer_name"]
            for customer in self.customers
        }

        customer_addresses = {
            customer["address"]
            for customer in self.customers
        }

        for scenario in self.scenarios["scenarios"]:
            document = (
                PROJECT_ROOT / scenario["document_path"]
            ).read_text(encoding="utf-8")

            # The synthetic reference customer used by this task is
            # expected in the generated clean/mismatch documents.
            if scenario["customer_id"] == "CUST-0001":
                self.assertIn("Aarav", document)

            for name in customer_names:
                if name != "Aarav Mehta":
                    self.assertNotIn(name, document)

            for address in customer_addresses:
                if address != "42 Example Avenue, Vijayawada":
                    self.assertNotIn(address, document)

    def test_document_directories_are_used(self) -> None:
        self.assertTrue(CLEAN_DIR.is_dir())
        self.assertTrue(MISMATCH_DIR.is_dir())

        clean_documents = list(CLEAN_DIR.glob("*.html"))
        mismatch_documents = list(MISMATCH_DIR.glob("*.html"))

        self.assertGreaterEqual(len(clean_documents), 1)
        self.assertGreaterEqual(len(mismatch_documents), 2)


if __name__ == "__main__":
    unittest.main()