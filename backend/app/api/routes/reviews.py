"""Role-protected human review API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import (
    ComplaintServiceDependency,
    ComplaintRepositoryDependency,
    PredictionRepositoryDependency,
    ReviewServiceDependency,
    TransactionalComplaintRepositoryDependency,
    TransactionalPredictionRepositoryDependency,
    TransactionalReviewServiceDependency,
)
from app.authz import ReviewerOrAdministratorUser
from app.models import Complaint, Prediction
from app.schemas import (
    ReviewActionRequest,
    ReviewClaimResponse,
    ReviewCorrectionRequest,
    ReviewQueueItemResponse,
    ReviewQueueResponse,
    ReviewResponse,
)
from app.schemas.review import ReviewerComplaintResponse
from app.services import ComplaintNotFoundError
from app.services import (
    DuplicateReviewError,
    InvalidReviewDataError,
    PredictionForReviewNotFoundError,
    ReviewAccessDeniedError,
    ReviewNotAllowedError,
    ReviewNotFoundError,
)


router = APIRouter(prefix="/reviews", tags=["Human Review"])


def _forbidden() -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, "Not enough permissions")


@router.get(
    "/complaints/{complaint_id}",
    response_model=ReviewerComplaintResponse,
)
async def get_reviewer_complaint(
    complaint_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    complaint_service: ComplaintServiceDependency,
) -> ReviewerComplaintResponse:
    del current_user
    try:
        complaint = await complaint_service.get_complaint(complaint_id)
    except ComplaintNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found",
        ) from None
    return ReviewerComplaintResponse.model_validate(complaint)


async def _resolve_target(
    complaint_id: UUID,
    prediction_id: UUID,
    complaint_repository,
    prediction_repository,
) -> tuple[Complaint, Prediction]:
    complaint = await complaint_repository.get_by_id(complaint_id)
    prediction = await prediction_repository.get_by_id(prediction_id)
    if complaint is None or prediction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review target not found")
    return complaint, prediction


def _translate_action_error(error: Exception) -> HTTPException:
    if isinstance(error, DuplicateReviewError):
        return HTTPException(status.HTTP_409_CONFLICT, "Prediction has already been reviewed")
    if isinstance(error, (ReviewNotAllowedError, PredictionForReviewNotFoundError)):
        return HTTPException(status.HTTP_409_CONFLICT, "Review action is not allowed")
    if isinstance(error, InvalidReviewDataError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid review data")
    return _forbidden()


@router.get("/queue", response_model=ReviewQueueResponse)
async def list_review_queue(
    current_user: ReviewerOrAdministratorUser,
    review_service: ReviewServiceDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> ReviewQueueResponse:
    complaints = await review_service.list_review_queue(offset=offset, limit=limit)
    return ReviewQueueResponse(
        items=[ReviewQueueItemResponse.model_validate(item) for item in complaints],
        offset=offset,
        limit=limit,
        count=len(complaints),
    )


@router.post("/complaints/{complaint_id}/claim", response_model=ReviewClaimResponse)
async def claim_review(
    complaint_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    complaint_repository: TransactionalComplaintRepositoryDependency,
    review_service: TransactionalReviewServiceDependency,
) -> ReviewClaimResponse:
    complaint = await complaint_repository.get_by_id(complaint_id)
    if complaint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complaint not found")
    try:
        complaint = await review_service.claim_review(
            complaint=complaint, reviewer=current_user
        )
    except ReviewNotAllowedError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Complaint cannot be claimed") from None
    except ReviewAccessDeniedError:
        raise _forbidden() from None
    return ReviewClaimResponse(
        complaint_id=complaint.id, current_status=complaint.current_status
    )


async def _perform_action(
    action: str,
    complaint_id: UUID,
    payload: ReviewActionRequest,
    current_user,
    complaint_repository,
    prediction_repository,
    review_service,
) -> ReviewResponse:
    complaint, prediction = await _resolve_target(
        complaint_id,
        payload.prediction_id,
        complaint_repository,
        prediction_repository,
    )
    try:
        if action == "correct":
            review = await review_service.correct_prediction(
                complaint=complaint,
                prediction=prediction,
                reviewer=current_user,
                category_id=payload.category_id,
                department_id=payload.department_id,
                urgency=payload.urgency,
                comment=payload.comment,
            )
        else:
            method = getattr(review_service, f"{action}_prediction")
            review = await method(
                complaint=complaint,
                prediction=prediction,
                reviewer=current_user,
                comment=payload.comment,
            )
    except (
        DuplicateReviewError,
        ReviewNotAllowedError,
        PredictionForReviewNotFoundError,
        InvalidReviewDataError,
        ReviewAccessDeniedError,
    ) as error:
        raise _translate_action_error(error) from None
    return ReviewResponse.model_validate(review)


@router.post("/complaints/{complaint_id}/approve", response_model=ReviewResponse)
async def approve_prediction(
    complaint_id: UUID,
    payload: ReviewActionRequest,
    current_user: ReviewerOrAdministratorUser,
    complaint_repository: TransactionalComplaintRepositoryDependency,
    prediction_repository: TransactionalPredictionRepositoryDependency,
    review_service: TransactionalReviewServiceDependency,
) -> ReviewResponse:
    return await _perform_action(
        "approve", complaint_id, payload, current_user, complaint_repository,
        prediction_repository, review_service
    )


@router.post("/complaints/{complaint_id}/correct", response_model=ReviewResponse)
async def correct_prediction(
    complaint_id: UUID,
    payload: ReviewCorrectionRequest,
    current_user: ReviewerOrAdministratorUser,
    complaint_repository: TransactionalComplaintRepositoryDependency,
    prediction_repository: TransactionalPredictionRepositoryDependency,
    review_service: TransactionalReviewServiceDependency,
) -> ReviewResponse:
    return await _perform_action(
        "correct", complaint_id, payload, current_user, complaint_repository,
        prediction_repository, review_service
    )


@router.post("/complaints/{complaint_id}/reject", response_model=ReviewResponse)
async def reject_prediction(
    complaint_id: UUID,
    payload: ReviewActionRequest,
    current_user: ReviewerOrAdministratorUser,
    complaint_repository: TransactionalComplaintRepositoryDependency,
    prediction_repository: TransactionalPredictionRepositoryDependency,
    review_service: TransactionalReviewServiceDependency,
) -> ReviewResponse:
    return await _perform_action(
        "reject", complaint_id, payload, current_user, complaint_repository,
        prediction_repository, review_service
    )


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    review_service: ReviewServiceDependency,
) -> ReviewResponse:
    try:
        review = await review_service.get_review(review_id)
    except ReviewNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Review not found") from None
    return ReviewResponse.model_validate(review)
