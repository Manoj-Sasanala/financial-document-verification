import pytest
from pydantic import ValidationError

from app.core.contracts import (
    CaseResult,
    FieldValue,
    Finding,
    MLResult,
    StageError,
)


def test_valid_field_value_serializes():
    value = FieldValue(
        raw_value="John Doe",
        status="present",
        source_page=1,
        source_reference="page-1",
    )

    data = value.model_dump()

    assert data["raw_value"] == "John Doe"
    assert data["status"] == "present"
    assert data["source_page"] == 1


def test_valid_finding_serializes():
    finding = Finding(
        field_name="customer_name",
        code="missing_name",
        reason="Customer name is missing",
        severity="high",
    )

    assert finding.model_dump()["code"] == "missing_name"


def test_valid_ml_result_serializes():
    result = MLResult(
        classification="consistent",
        model_version="1.0",
    )

    assert result.model_dump() == {
        "classification": "consistent",
        "model_version": "1.0",
    }


def test_stage_error_serializes():
    error = StageError(
        stage="validation",
        code="INVALID_FIELD",
        message="Invalid field",
        recoverable=True,
    )

    assert error.model_dump()["recoverable"] is True


def test_invalid_ml_classification_is_rejected():
    with pytest.raises(ValidationError):
        MLResult(
            classification="invalid",
            model_version="1.0",
        )


def test_case_result_rejects_unexpected_fields():
    with pytest.raises(ValidationError):
        FieldValue(
            raw_value="John Doe",
            status="present",
            unexpected_field="not_allowed",
        )