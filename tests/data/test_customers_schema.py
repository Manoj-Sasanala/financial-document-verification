import json
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "data" / "synthetic" / "customers.schema.json"


def load_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def assert_record_matches_frozen_shape(
    testcase: unittest.TestCase,
    record: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    """Perform focused validation of the frozen DATA-01 shape.

    This intentionally checks only the schema features used by DATA-01.
    Full JSON Schema validation is left to a future project need rather
    than adding a new runtime dependency for this task.
    """
    testcase.assertIsInstance(record, dict)

    required = schema["required"]
    properties = schema["properties"]

    testcase.assertEqual(set(record.keys()), set(required))

    for field_name in required:
        testcase.assertIn(field_name, properties)
        testcase.assertIn(field_name, record)

        field_schema = properties[field_name]

        if field_schema["type"] == "string":
            testcase.assertIsInstance(record[field_name], str)
            testcase.assertGreaterEqual(
                len(record[field_name]),
                field_schema["minLength"],
            )
            testcase.assertLessEqual(
                len(record[field_name]),
                field_schema["maxLength"],
            )


class TestCustomerSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_schema()

    def test_schema_file_loads(self) -> None:
        self.assertTrue(SCHEMA_PATH.is_file())
        self.assertEqual(self.schema["type"], "object")

    def test_required_fields_are_frozen(self) -> None:
        self.assertEqual(
            self.schema["required"],
            [
                "customer_id",
                "customer_name",
                "address",
                "postal_code",
            ],
        )

    def test_only_declared_customer_properties_are_allowed(self) -> None:
        self.assertFalse(self.schema["additionalProperties"])

        self.assertEqual(
            set(self.schema["properties"].keys()),
            {
                "customer_id",
                "customer_name",
                "address",
                "postal_code",
            },
        )

    def test_all_reference_fields_are_strings(self) -> None:
        for field_name in self.schema["required"]:
            self.assertEqual(
                self.schema["properties"][field_name]["type"],
                "string",
            )

    def test_clean_customer_record_is_representable(self) -> None:
        clean_customer = {
            "customer_id": "CUST-0001",
            "customer_name": "Aarav Mehta",
            "address": "12 Example Street, Vijayawada",
            "postal_code": "520010",
        }

        assert_record_matches_frozen_shape(
            self,
            clean_customer,
            self.schema,
        )

    def test_name_mismatch_value_is_representable(self) -> None:
        mismatch_customer = {
            "customer_id": "CUST-0001",
            "customer_name": "Aarav Sharma",
            "address": "12 Example Street, Vijayawada",
            "postal_code": "520010",
        }

        assert_record_matches_frozen_shape(
            self,
            mismatch_customer,
            self.schema,
        )

        self.assertNotEqual(
            mismatch_customer["customer_name"],
            "Aarav Mehta",
        )

    def test_address_mismatch_value_is_representable(self) -> None:
        mismatch_customer = {
            "customer_id": "CUST-0001",
            "customer_name": "Aarav Mehta",
            "address": "99 Different Street, Vijayawada",
            "postal_code": "520010",
        }

        assert_record_matches_frozen_shape(
            self,
            mismatch_customer,
            self.schema,
        )

        self.assertNotEqual(
            mismatch_customer["address"],
            "12 Example Street, Vijayawada",
        )

    def test_postal_code_mismatch_value_is_representable(self) -> None:
        mismatch_customer = {
            "customer_id": "CUST-0001",
            "customer_name": "Aarav Mehta",
            "address": "12 Example Street, Vijayawada",
            "postal_code": "520011",
        }

        assert_record_matches_frozen_shape(
            self,
            mismatch_customer,
            self.schema,
        )

        self.assertNotEqual(
            mismatch_customer["postal_code"],
            "520010",
        )

    def test_missing_required_field_is_rejected_by_frozen_shape(self) -> None:
        incomplete_customer = {
            "customer_id": "CUST-0001",
            "customer_name": "Aarav Mehta",
            "postal_code": "520010",
        }

        with self.assertRaises(AssertionError):
            assert_record_matches_frozen_shape(
                self,
                incomplete_customer,
                self.schema,
            )

    def test_extra_field_is_rejected_by_frozen_shape(self) -> None:
        customer_with_extra_field = {
            "customer_id": "CUST-0001",
            "customer_name": "Aarav Mehta",
            "address": "12 Example Street, Vijayawada",
            "postal_code": "520010",
            "risk_score": 50,
        }

        with self.assertRaises(AssertionError):
            assert_record_matches_frozen_shape(
                self,
                customer_with_extra_field,
                self.schema,
            )


if __name__ == "__main__":
    unittest.main()