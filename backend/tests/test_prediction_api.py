"""Prediction API and dependency regression tests."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.dependencies import (
    get_complaint_predictor,
    get_model_version_repository,
    get_prediction_service,
    get_transactional_model_version_repository,
    get_transactional_prediction_service,
)
from app.api.routes.predictions import (
    get_prediction,
    list_complaint_predictions,
    run_prediction,
)
from app.core.config import Settings
from app.main import create_app
from app.models import (
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    ComplaintUrgency,
    Department,
    ModelType,
    ModelVersion,
    Prediction,
    User,
)
from app.prediction import ComplaintPredictor
from app.repositories import ModelVersionRepository
from app.schemas import PredictionRunRequest
from app.services import (
    ActiveModelVersionNotFoundError,
    ComplaintNotFoundError,
    DuplicatePredictionError,
    PredictionExecutionError,
    PredictionNotAllowedError,
    PredictionNotFoundError,
)


def prediction() -> Prediction:
    model_version = ModelVersion(
        id=uuid4(), name="Router", version="v1", model_type=ModelType.TFIDF_CLASSIFIER
    )
    category = ComplaintCategory(
        id=uuid4(), code="card", display_name="Card dispute", is_active=True
    )
    department = Department(
        id=uuid4(), code="cards", display_name="Cards", is_active=True
    )
    return Prediction(
        id=uuid4(), complaint_id=uuid4(), model_version_id=model_version.id,
        predicted_category_id=category.id, predicted_department_id=department.id,
        predicted_urgency=ComplaintUrgency.HIGH,
        confidence_score=Decimal("0.82000"), output_valid=True,
        failure_code=None, failure_message="hidden", raw_output={"hidden": True},
        inference_latency_ms=None, created_at=datetime.now(timezone.utc),
        model_version=model_version,
        predicted_category=category,
        predicted_department=department,
    )


@pytest.mark.anyio
async def test_customer_runs_owned_complaint_and_response_is_safe() -> None:
    customer = User(id=uuid4())
    complaint = Complaint(id=uuid4(), current_status=ComplaintStatus.AWAITING_REVIEW)
    item = prediction()
    complaint_service = MagicMock()
    complaint_service.get_customer_complaint = AsyncMock(return_value=complaint)
    service = MagicMock()
    service.predict_complaint = AsyncMock(return_value=item)
    response = await run_prediction(
        complaint.id, customer, complaint_service, service,
        PredictionRunRequest(model_type=ModelType.TFIDF_CLASSIFIER),
    )
    complaint_service.get_customer_complaint.assert_awaited_once_with(
        complaint_id=complaint.id, customer_id=customer.id
    )
    service.predict_complaint.assert_awaited_once_with(
        complaint=complaint, model_type=ModelType.TFIDF_CLASSIFIER
    )
    assert response.complaint_status is ComplaintStatus.AWAITING_REVIEW
    assert "raw_output" not in response.prediction.model_dump()
    assert "failure_message" not in response.prediction.model_dump()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "code", "detail"),
    [
        (ComplaintNotFoundError("hidden"), 404, "Complaint not found"),
        (DuplicatePredictionError("hidden"), 409, "Prediction has already been completed"),
        (PredictionNotAllowedError("hidden"), 409, "Complaint cannot be predicted in its current state"),
        (ActiveModelVersionNotFoundError("hidden"), 503, "No active prediction model is available"),
        (PredictionExecutionError("hidden"), 500, "Prediction execution failed"),
    ],
)
async def test_run_errors_are_generic(error, code, detail) -> None:
    complaint_service = MagicMock()
    complaint_service.get_customer_complaint = AsyncMock(side_effect=error)
    with pytest.raises(HTTPException) as caught:
        await run_prediction(
            uuid4(), User(id=uuid4()), complaint_service, MagicMock(),
            PredictionRunRequest(),
        )
    assert (caught.value.status_code, caught.value.detail) == (code, detail)


@pytest.mark.anyio
async def test_read_routes_return_safe_fields_and_pagination() -> None:
    item = prediction()
    service = MagicMock()
    service.get_prediction = AsyncMock(return_value=item)
    service.list_complaint_predictions = AsyncMock(return_value=[item])
    user = User(id=uuid4())
    assert (await get_prediction(item.id, user, service)).id == item.id
    listed = await list_complaint_predictions(item.complaint_id, user, service, 3, 7)
    assert (listed.offset, listed.limit, listed.count) == (3, 7, 1)
    assert "raw_output" not in listed.items[0].model_dump()
    assert listed.items[0].category.name == "Card dispute"
    assert listed.items[0].department.name == "Cards"
    assert listed.items[0].model_version.name == "Router"
    assert listed.items[0].predicted_category_id == item.predicted_category_id
    assert listed.items[0].predicted_department_id == item.predicted_department_id
    assert listed.items[0].model_version_id == item.model_version_id
    service.list_complaint_predictions.assert_awaited_once_with(
        complaint_id=item.complaint_id, offset=3, limit=7
    )
    service.get_prediction.side_effect = PredictionNotFoundError("hidden")
    with pytest.raises(HTTPException) as caught:
        await get_prediction(uuid4(), user, service)
    assert caught.value.status_code == 404


@pytest.mark.anyio
async def test_dependency_construction_is_fresh_exact_and_neutral() -> None:
    session = MagicMock()
    assert (await get_model_version_repository(session)).session is session
    assert (await get_transactional_model_version_repository(session)).session is session
    first, second = get_complaint_predictor(), get_complaint_predictor()
    assert isinstance(first, ComplaintPredictor) and first is not second
    dependencies = [MagicMock() for _ in range(5)]
    read = get_prediction_service(*dependencies)
    transactional = get_transactional_prediction_service(*dependencies)
    assert read is not transactional
    assert isinstance(read._model_version_repository, MagicMock)
    assert session.mock_calls == []


def test_openapi_contract_has_safe_prediction_surface() -> None:
    schema = create_app(Settings()).openapi()
    paths = schema["paths"]
    assert "post" in paths["/api/predictions/complaints/{complaint_id}/run"]
    assert "get" in paths["/api/predictions/complaints/{complaint_id}"]
    assert "get" in paths["/api/predictions/{prediction_id}"]
    properties = schema["components"]["schemas"]["PredictionResponse"]["properties"]
    assert "raw_output" not in properties and "failure_message" not in properties
    reviewer_properties = schema["components"]["schemas"]["ReviewerPredictionResponse"]["properties"]
    assert {"category", "department", "model_version"} <= set(reviewer_properties)
    assert not any("upload" in path for path in paths)
    assert not any("run" in path for path in paths if "benchmark" in path)
