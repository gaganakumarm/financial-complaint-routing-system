"""Prediction execution and safe evidence API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query, status

from app.api.dependencies import (
    PredictionServiceDependency,
    TransactionalComplaintServiceDependency,
    TransactionalPredictionServiceDependency,
)
from app.authz import CustomerUser, ReviewerOrAdministratorUser
from app.prediction import PredictorConfigurationError
from app.schemas import (
    PredictionListResponse,
    PredictionResponse,
    PredictionRunRequest,
    PredictionRunResponse,
)
from app.services import (
    ActiveModelVersionNotFoundError,
    ComplaintAccessDeniedError,
    ComplaintNotFoundError,
    DuplicatePredictionError,
    InvalidPredictionOutputError,
    PredictionExecutionError,
    PredictionNotAllowedError,
    PredictionNotFoundError,
)


router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.post(
    "/complaints/{complaint_id}/run",
    response_model=PredictionRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_prediction(
    complaint_id: UUID,
    current_user: CustomerUser,
    complaint_service: TransactionalComplaintServiceDependency,
    prediction_service: TransactionalPredictionServiceDependency,
    payload: Annotated[PredictionRunRequest, Body()] = PredictionRunRequest(),
) -> PredictionRunResponse:
    try:
        complaint = await complaint_service.get_customer_complaint(
            complaint_id=complaint_id,
            customer_id=current_user.id,
        )
        prediction = await prediction_service.predict_complaint(
            complaint=complaint,
            model_type=payload.model_type,
        )
    except (ComplaintNotFoundError, ComplaintAccessDeniedError):
        raise HTTPException(status_code=404, detail="Complaint not found") from None
    except ActiveModelVersionNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="No active prediction model is available",
        ) from None
    except DuplicatePredictionError:
        raise HTTPException(
            status_code=409,
            detail="Prediction has already been completed",
        ) from None
    except PredictionNotAllowedError:
        raise HTTPException(
            status_code=409,
            detail="Complaint cannot be predicted in its current state",
        ) from None
    except (
        InvalidPredictionOutputError,
        PredictionExecutionError,
        PredictorConfigurationError,
    ):
        raise HTTPException(
            status_code=500,
            detail="Prediction execution failed",
        ) from None
    return PredictionRunResponse(
        prediction=PredictionResponse.model_validate(prediction),
        complaint_status=complaint.current_status,
    )


@router.get("/complaints/{complaint_id}", response_model=PredictionListResponse)
async def list_complaint_predictions(
    complaint_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    prediction_service: PredictionServiceDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> PredictionListResponse:
    del current_user
    predictions = await prediction_service.list_complaint_predictions(
        complaint_id=complaint_id,
        offset=offset,
        limit=limit,
    )
    return PredictionListResponse(
        items=[PredictionResponse.model_validate(item) for item in predictions],
        offset=offset,
        limit=limit,
        count=len(predictions),
    )


@router.get("/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(
    prediction_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    prediction_service: PredictionServiceDependency,
) -> PredictionResponse:
    del current_user
    try:
        prediction = await prediction_service.get_prediction(prediction_id)
    except PredictionNotFoundError:
        raise HTTPException(status_code=404, detail="Prediction not found") from None
    return PredictionResponse.model_validate(prediction)
