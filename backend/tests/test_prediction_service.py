"""Tests for transaction-neutral prediction lifecycle orchestration."""

from dataclasses import FrozenInstanceError
from math import inf, nan
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from app.models import (
    Complaint,
    ComplaintChangeSource,
    ComplaintStatus,
    ComplaintUrgency,
    ModelType,
    ModelVersion,
    Prediction,
)
from app.prediction import ComplaintPredictor, PredictionOutput
from app.repositories import (
    ComplaintRepository,
    ModelVersionRepository,
    PredictionRepository,
)
from app.services import (
    ActiveModelVersionNotFoundError,
    ComplaintService,
    DuplicatePredictionError,
    InvalidPredictionOutputError,
    PredictionExecutionError,
    PredictionNotAllowedError,
    PredictionNotFoundError,
    PredictionService,
)


class FakePredictor:
    def __init__(self, output=None, error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls = []

    async def predict(self, *, complaint, model_version):
        self.calls.append((complaint, model_version))
        if self.error:
            raise self.error
        return self.output


def _complaint(status=ComplaintStatus.SUBMITTED, *, with_id=True) -> Complaint:
    return Complaint(
        id=uuid4() if with_id else None,
        reference_number="FCR-TEST",
        customer_id=uuid4(),
        title="Private title",
        description="Private description",
        current_status=status,
        final_category_id=None,
        final_department_id=None,
        final_urgency=None,
    )


def _model(*, active=True, approved=True, model_type=ModelType.HYBRID):
    return ModelVersion(
        id=uuid4(), name="model", version="1", model_type=model_type,
        is_active=active, is_approved=approved,
    )


def _output(confidence=0.5):
    return PredictionOutput(
        category_id=uuid4(), department_id=uuid4(),
        confidence_score=confidence, urgency=ComplaintUrgency.HIGH,
        raw_output={"label": "safe"},
    )


def _service(*, output=None, threshold=0.9, predictor=None):
    complaint_repository = MagicMock(spec=ComplaintRepository)
    model_repository = MagicMock(spec=ModelVersionRepository)
    prediction_repository = MagicMock(spec=PredictionRepository)
    complaint_service = MagicMock(spec=ComplaintService)
    predictor = predictor or FakePredictor(output or _output())
    service = PredictionService(
        complaint_repository=complaint_repository,
        model_version_repository=model_repository,
        prediction_repository=prediction_repository,
        complaint_service=complaint_service,
        predictor=predictor,
        auto_route_confidence_threshold=threshold,
    )
    return service, complaint_repository, model_repository, prediction_repository, complaint_service, predictor


def test_prediction_contract_is_frozen_slotted_and_runtime_checkable() -> None:
    output = _output()
    with pytest.raises(FrozenInstanceError):
        output.confidence_score = 0.2
    assert not hasattr(output, "__dict__")
    assert isinstance(FakePredictor(output), ComplaintPredictor)
    assert not isinstance(object(), ComplaintPredictor)


@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_constructor_accepts_threshold_boundaries_and_preserves_dependencies(threshold) -> None:
    service, complaint_repo, model_repo, prediction_repo, complaint_service, predictor = _service(threshold=threshold)
    assert service._complaint_repository is complaint_repo
    assert service._model_version_repository is model_repo
    assert service._prediction_repository is prediction_repo
    assert service._complaint_service is complaint_service
    assert service._predictor is predictor
    assert not complaint_repo.mock_calls


@pytest.mark.parametrize("threshold", [-0.1, 1.1, True, "0.5", nan, inf])
def test_constructor_rejects_invalid_threshold(threshold) -> None:
    with pytest.raises(ValueError):
        _service(threshold=threshold)


@pytest.mark.parametrize(
    "status",
    [
        ComplaintStatus.PREDICTION_PENDING,
        ComplaintStatus.PREDICTION_FAILED,
        ComplaintStatus.PREDICTION_COMPLETED,
        ComplaintStatus.AWAITING_REVIEW,
        ComplaintStatus.UNDER_REVIEW,
        ComplaintStatus.ROUTED,
        ComplaintStatus.CLOSED,
    ],
)
def test_ineligible_statuses_are_rejected_without_mutation(status) -> None:
    service, _, _, prediction_repo, complaint_service, predictor = _service()
    with pytest.raises(PredictionNotAllowedError):
        service._validate_prediction_allowed(_complaint(status))
    assert not prediction_repo.mock_calls
    assert not complaint_service.mock_calls
    assert not predictor.calls


def test_submitted_is_eligible_but_missing_id_is_not() -> None:
    PredictionService._validate_prediction_allowed(_complaint())
    with pytest.raises(PredictionNotAllowedError):
        PredictionService._validate_prediction_allowed(_complaint(with_id=False))


@pytest.mark.anyio
async def test_active_model_selection_checks_type_and_active_state() -> None:
    service, _, model_repo, _, _, _ = _service()
    active = _model(model_type=ModelType.HYBRID)
    model_repo.get_active = AsyncMock(return_value=active)
    assert await service._get_active_model_version(model_type=ModelType.HYBRID) is active
    for unavailable in (None, _model(active=False), _model(approved=False)):
        model_repo.get_active.return_value = unavailable
        with pytest.raises(ActiveModelVersionNotFoundError):
            await service._get_active_model_version()
    model_repo.get_active.return_value = active
    with pytest.raises(ActiveModelVersionNotFoundError):
        await service._get_active_model_version(model_type=ModelType.PROMPTED_LLM)


@pytest.mark.parametrize("confidence", [0.0, 1.0, 0.75])
def test_valid_output_is_returned_unchanged(confidence) -> None:
    output = _output(confidence)
    assert PredictionService._validate_prediction_output(output) is output


@pytest.mark.parametrize("confidence", [-0.1, 1.1, nan, inf, -inf, True, "0.5"])
def test_invalid_confidence_is_rejected(confidence) -> None:
    with pytest.raises(InvalidPredictionOutputError):
        PredictionService._validate_prediction_output(_output(confidence))


def test_other_invalid_output_fields_are_rejected() -> None:
    valid = _output()
    invalid = [
        object(),
        PredictionOutput("bad", valid.department_id, 0.5, valid.urgency),
        PredictionOutput(valid.category_id, "bad", 0.5, valid.urgency),
        PredictionOutput(valid.category_id, valid.department_id, 0.5, "high"),
        PredictionOutput(valid.category_id, valid.department_id, 0.5, valid.urgency, []),
        PredictionOutput(
            valid.category_id,
            valid.department_id,
            0.5,
            valid.urgency,
            {"not_json": object()},
        ),
    ]
    for output in invalid:
        with pytest.raises(InvalidPredictionOutputError):
            PredictionService._validate_prediction_output(output)


@pytest.mark.anyio
async def test_duplicate_usable_prediction_stops_before_transition() -> None:
    complaint = _complaint()
    model = _model()
    existing = Prediction(model_version_id=model.id, output_valid=True)
    service, _, model_repo, prediction_repo, complaint_service, predictor = _service()
    model_repo.get_active = AsyncMock(return_value=model)
    prediction_repo.list_for_complaint = AsyncMock(return_value=[existing])
    with pytest.raises(DuplicatePredictionError):
        await service.predict_complaint(complaint=complaint)
    assert not complaint_service.mock_calls
    assert not predictor.calls


@pytest.mark.anyio
async def test_successful_prediction_persists_and_enters_review_in_order() -> None:
    complaint = _complaint()
    model = _model()
    output = _output(0.95)
    service, complaint_repo, model_repo, prediction_repo, complaint_service, predictor = _service(output=output)
    model_repo.get_active = AsyncMock(return_value=model)
    prediction_repo.list_for_complaint = AsyncMock(return_value=[])
    prediction_repo.add = AsyncMock(side_effect=lambda item: item)
    prediction_repo.flush = AsyncMock()
    prediction_repo.refresh = AsyncMock(side_effect=lambda item: item)
    complaint_service.transition_status = AsyncMock(side_effect=lambda **kwargs: kwargs["complaint"])

    prediction = await service.predict_complaint(complaint=complaint)

    assert predictor.calls == [(complaint, model)]
    assert prediction.output_valid is True
    assert prediction.predicted_category_id == output.category_id
    prediction_repo.add.assert_awaited_once_with(prediction)
    prediction_repo.flush.assert_awaited_once_with()
    prediction_repo.refresh.assert_awaited_once_with(prediction)
    assert [item.kwargs["new_status"] for item in complaint_service.transition_status.await_args_list] == [
        ComplaintStatus.PREDICTION_PENDING,
        ComplaintStatus.PREDICTION_COMPLETED,
        ComplaintStatus.AWAITING_REVIEW,
    ]
    assert all(item.kwargs["source"] is ComplaintChangeSource.MODEL_PIPELINE for item in complaint_service.transition_status.await_args_list)
    assert not complaint_repo.mock_calls
    for repository in (complaint_repo, model_repo, prediction_repo):
        for method in ("commit", "rollback", "begin"):
            getattr(repository, method, MagicMock()).assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("predictor", "exception_type"),
    [
        (FakePredictor(error=RuntimeError("secret predictor detail")), PredictionExecutionError),
        (FakePredictor(output=_output(nan)), InvalidPredictionOutputError),
    ],
)
async def test_failures_transition_to_review_without_persistence(predictor, exception_type) -> None:
    complaint = _complaint()
    model = _model()
    service, _, model_repo, prediction_repo, complaint_service, _ = _service(predictor=predictor)
    model_repo.get_active = AsyncMock(return_value=model)
    prediction_repo.list_for_complaint = AsyncMock(return_value=[])
    complaint_service.transition_status = AsyncMock(side_effect=lambda **kwargs: kwargs["complaint"])
    with pytest.raises(exception_type) as caught:
        await service.predict_complaint(complaint=complaint)
    assert "secret" not in str(caught.value)
    assert [item.kwargs["new_status"] for item in complaint_service.transition_status.await_args_list] == [
        ComplaintStatus.PREDICTION_PENDING,
        ComplaintStatus.PREDICTION_FAILED,
        ComplaintStatus.AWAITING_REVIEW,
    ]
    prediction_repo.add.assert_not_called()


@pytest.mark.anyio
async def test_read_methods_return_exact_repository_results() -> None:
    service, _, _, repository, _, _ = _service()
    prediction = Prediction(id=uuid4())
    repository.get_by_id = AsyncMock(return_value=prediction)
    assert await service.get_prediction(prediction.id) is prediction
    repository.get_by_id.return_value = None
    with pytest.raises(PredictionNotFoundError):
        await service.get_prediction(uuid4())
    items = [prediction]
    repository.list_for_complaint = AsyncMock(return_value=items)
    complaint_id = uuid4()
    assert await service.list_complaint_predictions(complaint_id=complaint_id, offset=2, limit=7) is items
    repository.list_for_complaint.assert_awaited_once_with(complaint_id, offset=2, limit=7)
