"""Transaction-neutral complaint prediction lifecycle orchestration."""

from decimal import Decimal
import json
from math import isfinite
from numbers import Real
from uuid import UUID

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
from app.services.complaint import ComplaintService


class PredictionServiceError(Exception):
    """Base exception for prediction service failures."""


class PredictionNotAllowedError(PredictionServiceError):
    """Raised when the complaint is not eligible for prediction."""


class ActiveModelVersionNotFoundError(PredictionServiceError):
    """Raised when no suitable active model exists."""


class DuplicatePredictionError(PredictionServiceError):
    """Raised when a usable prediction already exists."""


class InvalidPredictionOutputError(PredictionServiceError):
    """Raised when predictor output violates the application contract."""


class PredictionExecutionError(PredictionServiceError):
    """Raised when predictor execution fails."""


class PredictionNotFoundError(PredictionServiceError):
    """Raised when a prediction cannot be found."""


_NOT_ALLOWED = "Prediction is not allowed."
_NO_ACTIVE_MODEL = "Active model version was not found."
_DUPLICATE = "A usable prediction already exists."
_INVALID_OUTPUT = "Prediction output is invalid."
_EXECUTION_FAILED = "Prediction execution failed."
_NOT_FOUND = "Prediction was not found."


class PredictionService:
    """Coordinate predictor execution and persistence without owning transactions."""

    def __init__(
        self,
        *,
        complaint_repository: ComplaintRepository,
        model_version_repository: ModelVersionRepository,
        prediction_repository: PredictionRepository,
        complaint_service: ComplaintService,
        predictor: ComplaintPredictor,
        auto_route_confidence_threshold: float = 0.90,
    ) -> None:
        if (
            isinstance(auto_route_confidence_threshold, bool)
            or not isinstance(auto_route_confidence_threshold, Real)
            or not isfinite(float(auto_route_confidence_threshold))
            or not 0.0 <= float(auto_route_confidence_threshold) <= 1.0
        ):
            raise ValueError("auto-route confidence threshold must be between 0 and 1")
        self._complaint_repository = complaint_repository
        self._model_version_repository = model_version_repository
        self._prediction_repository = prediction_repository
        self._complaint_service = complaint_service
        self._predictor = predictor
        self._auto_route_confidence_threshold = float(
            auto_route_confidence_threshold
        )

    async def _get_active_model_version(
        self,
        *,
        model_type: ModelType | None = None,
    ) -> ModelVersion:
        model_version = await self._model_version_repository.get_active()
        if (
            model_version is None
            or not model_version.is_active
            or not model_version.is_approved
            or (model_type is not None and model_version.model_type is not model_type)
        ):
            raise ActiveModelVersionNotFoundError(_NO_ACTIVE_MODEL)
        return model_version

    @staticmethod
    def _validate_prediction_allowed(complaint: Complaint) -> None:
        # The existing complaint transition graph has no
        # prediction_failed -> prediction_pending transition, so retries cannot
        # safely be admitted until that domain rule is introduced.
        if (
            not isinstance(complaint.__dict__.get("id"), UUID)
            or complaint.current_status is not ComplaintStatus.SUBMITTED
        ):
            raise PredictionNotAllowedError(_NOT_ALLOWED)

    @staticmethod
    def _validate_prediction_output(output: PredictionOutput) -> PredictionOutput:
        if not isinstance(output, PredictionOutput):
            raise InvalidPredictionOutputError(_INVALID_OUTPUT)
        confidence = output.confidence_score
        if (
            not isinstance(output.category_id, UUID)
            or not isinstance(output.department_id, UUID)
            or isinstance(confidence, bool)
            or not isinstance(confidence, Real)
            or not isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
            or not isinstance(output.urgency, ComplaintUrgency)
            or (output.raw_output is not None and not isinstance(output.raw_output, dict))
        ):
            raise InvalidPredictionOutputError(_INVALID_OUTPUT)
        if output.raw_output is not None:
            try:
                json.dumps(output.raw_output, allow_nan=False)
            except (TypeError, ValueError):
                raise InvalidPredictionOutputError(_INVALID_OUTPUT) from None
        return output

    async def _ensure_not_duplicate(
        self,
        *,
        complaint_id: UUID,
        model_version_id: UUID,
    ) -> None:
        predictions = await self._prediction_repository.list_for_complaint(
            complaint_id,
            offset=0,
            limit=500,
        )
        if any(
            prediction.model_version_id == model_version_id
            and prediction.output_valid
            for prediction in predictions
        ):
            raise DuplicatePredictionError(_DUPLICATE)

    async def _transition(
        self, complaint: Complaint, status: ComplaintStatus
    ) -> Complaint:
        return await self._complaint_service.transition_status(
            complaint=complaint,
            new_status=status,
            changed_by_user_id=None,
            source=ComplaintChangeSource.MODEL_PIPELINE,
        )

    async def _record_failure(self, complaint: Complaint) -> None:
        await self._transition(complaint, ComplaintStatus.PREDICTION_FAILED)
        await self._transition(complaint, ComplaintStatus.AWAITING_REVIEW)

    async def predict_complaint(
        self,
        *,
        complaint: Complaint,
        model_type: ModelType | None = None,
    ) -> Prediction:
        self._validate_prediction_allowed(complaint)
        model_version = await self._get_active_model_version(model_type=model_type)
        complaint_id = complaint.id
        model_version_id = model_version.__dict__.get("id")
        if not isinstance(model_version_id, UUID):
            raise ActiveModelVersionNotFoundError(_NO_ACTIVE_MODEL)
        await self._ensure_not_duplicate(
            complaint_id=complaint_id,
            model_version_id=model_version_id,
        )
        await self._transition(complaint, ComplaintStatus.PREDICTION_PENDING)
        try:
            output = await self._predictor.predict(
                complaint=complaint,
                model_version=model_version,
            )
        except Exception:
            await self._record_failure(complaint)
            raise PredictionExecutionError(_EXECUTION_FAILED) from None
        try:
            output = self._validate_prediction_output(output)
        except InvalidPredictionOutputError:
            await self._record_failure(complaint)
            raise

        prediction = Prediction(
            complaint_id=complaint_id,
            model_version_id=model_version_id,
            predicted_category_id=output.category_id,
            predicted_department_id=output.department_id,
            predicted_urgency=output.urgency,
            confidence_score=Decimal(str(output.confidence_score)),
            raw_output=output.raw_output,
            output_valid=True,
            failure_code=None,
            failure_message=None,
            inference_latency_ms=None,
        )
        await self._prediction_repository.add(prediction)
        await self._prediction_repository.flush()
        prediction = await self._prediction_repository.refresh(prediction)
        await self._transition(complaint, ComplaintStatus.PREDICTION_COMPLETED)

        # Automated routing cannot supply the real user UUID currently required by
        # ComplaintService.assign_routing, so every valid result safely enters review.
        await self._transition(complaint, ComplaintStatus.AWAITING_REVIEW)
        return prediction

    async def get_prediction(self, prediction_id: UUID) -> Prediction:
        prediction = await self._prediction_repository.get_by_id(prediction_id)
        if prediction is None:
            raise PredictionNotFoundError(_NOT_FOUND)
        return prediction

    async def list_complaint_predictions(
        self,
        *,
        complaint_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Prediction]:
        return await self._prediction_repository.list_for_complaint(
            complaint_id,
            offset=offset,
            limit=limit,
        )
