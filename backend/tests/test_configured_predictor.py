"""Tests for the deterministic configured predictor."""

from copy import deepcopy
from math import inf, nan
from uuid import uuid4

import pytest

from app.models import Complaint, ComplaintUrgency, ModelVersion
from app.prediction import (
    ComplaintPredictor,
    ConfiguredBaselinePredictor,
    PredictorConfigurationError,
)


def objects(configuration=None):
    category, department, fallback_category, fallback_department = (
        uuid4(), uuid4(), uuid4(), uuid4()
    )
    config = configuration or {
        "default_category_id": str(fallback_category),
        "default_department_id": str(fallback_department),
        "default_urgency": "medium",
        "default_confidence_score": 0.7,
        "keyword_rules": [{
            "keywords": ["unauthorized", "fraud"],
            "category_id": str(category),
            "department_id": str(department),
            "urgency": "high",
            "confidence_score": 0.82,
        }],
    }
    complaint = Complaint(title="Card issue", description="UNKNOWN Unauthorized debit")
    return complaint, ModelVersion(configuration=config), config


@pytest.mark.anyio
async def test_protocol_matching_defaults_and_safe_diagnostics() -> None:
    predictor = ConfiguredBaselinePredictor()
    assert isinstance(predictor, ComplaintPredictor)
    complaint, model, config = objects()
    original = deepcopy(config)
    output = await predictor.predict(complaint=complaint, model_version=model)
    assert output.urgency is ComplaintUrgency.HIGH
    assert output.confidence_score == 0.82
    assert output.raw_output == {
        "predictor": "configured_baseline",
        "matched_rule_index": 0,
        "matched_keywords": ["unauthorized"],
    }
    assert complaint.title not in str(output.raw_output)
    assert complaint.description not in str(output.raw_output)
    assert config == original

    complaint.title, complaint.description = "Ordinary", "service enquiry"
    fallback = await predictor.predict(complaint=complaint, model_version=model)
    assert fallback.urgency is ComplaintUrgency.MEDIUM
    assert fallback.confidence_score == 0.7


@pytest.mark.anyio
async def test_first_matching_rule_wins_and_title_is_considered() -> None:
    complaint, model, config = objects()
    config["keyword_rules"].insert(0, {
        "keywords": ["card"],
        "category_id": str(uuid4()),
        "department_id": str(uuid4()),
        "urgency": "critical",
        "confidence_score": 0.9,
    })
    output = await ConfiguredBaselinePredictor().predict(
        complaint=complaint, model_version=model
    )
    assert output.raw_output["matched_rule_index"] == 0
    assert output.urgency is ComplaintUrgency.CRITICAL


@pytest.mark.anyio
@pytest.mark.parametrize("configuration", [None, [], "bad"])
async def test_configuration_must_be_dictionary(configuration) -> None:
    complaint, model, _ = objects()
    model.configuration = configuration
    with pytest.raises(PredictorConfigurationError, match="configuration is invalid"):
        await ConfiguredBaselinePredictor().predict(
            complaint=complaint, model_version=model
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("default_category_id", "bad"),
        ("default_urgency", "urgent"),
        ("default_confidence_score", True),
        ("default_confidence_score", nan),
        ("default_confidence_score", inf),
        ("default_confidence_score", -0.1),
        ("default_confidence_score", 1.1),
    ],
)
async def test_invalid_default_values_are_rejected(field, value) -> None:
    complaint, model, config = objects()
    config[field] = value
    with pytest.raises(PredictorConfigurationError):
        await ConfiguredBaselinePredictor().predict(
            complaint=complaint, model_version=model
        )


@pytest.mark.anyio
async def test_missing_default_and_invalid_rules_are_rejected() -> None:
    complaint, model, config = objects()
    del config["default_category_id"]
    with pytest.raises(PredictorConfigurationError):
        await ConfiguredBaselinePredictor().predict(complaint=complaint, model_version=model)
    _, model, config = objects()
    config["keyword_rules"] = [{"keywords": [" "]}]
    with pytest.raises(PredictorConfigurationError):
        await ConfiguredBaselinePredictor().predict(complaint=complaint, model_version=model)
