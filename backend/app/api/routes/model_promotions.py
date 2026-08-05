"""Model-promotion workflow REST API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import (
    ModelPromotionServiceDependency,
    TransactionalModelPromotionServiceDependency,
)
from app.authz import AdministratorUser, ReviewerOrAdministratorUser
from app.models import ModelPromotionStatus
from app.schemas import (
    ModelPromotionCancelRequest,
    ModelPromotionCreateRequest,
    ModelPromotionListResponse,
    ModelPromotionResponse,
    ModelPromotionReviewRequest,
)
from app.services import (
    BenchmarkComparisonNotFoundForPromotionError,
    BenchmarkResultModelMismatchError,
    BenchmarkResultNotFoundForPromotionError,
    BenchmarkResultNotInComparisonError,
    DuplicatePendingModelPromotionError,
    InvalidModelPromotionError,
    ModelPromotionCancelInput,
    ModelPromotionCreateInput,
    ModelPromotionNotFoundError,
    ModelPromotionPersistenceError,
    ModelPromotionReviewInput,
    ModelPromotionStateConflictError,
    NonWinningResultRequiresOverrideError,
)


router = APIRouter(prefix="/model-promotions", tags=["Model Promotions"])

_SERVICE_ERRORS = (
    ModelPromotionNotFoundError,
    BenchmarkComparisonNotFoundForPromotionError,
    BenchmarkResultNotFoundForPromotionError,
    InvalidModelPromotionError,
    BenchmarkResultNotInComparisonError,
    BenchmarkResultModelMismatchError,
    NonWinningResultRequiresOverrideError,
    DuplicatePendingModelPromotionError,
    ModelPromotionStateConflictError,
    ModelPromotionPersistenceError,
)


def _translate_error(error: Exception) -> HTTPException:
    mappings = (
        (ModelPromotionNotFoundError, 404, "Model promotion not found"),
        (BenchmarkComparisonNotFoundForPromotionError, 404, "Benchmark comparison not found"),
        (BenchmarkResultNotFoundForPromotionError, 404, "Benchmark result not found"),
        (InvalidModelPromotionError, 422, "Invalid model promotion"),
        (BenchmarkResultNotInComparisonError, 409, "Benchmark result does not belong to the comparison"),
        (BenchmarkResultModelMismatchError, 409, "Benchmark result and model version do not match"),
        (NonWinningResultRequiresOverrideError, 409, "Selecting a non-winning result requires an override"),
        (DuplicatePendingModelPromotionError, 409, "A pending model promotion already exists for this comparison"),
        (ModelPromotionStateConflictError, 409, "Model promotion state does not allow this operation"),
        (ModelPromotionPersistenceError, 500, "Model promotion could not be persisted"),
    )
    for error_type, status_code, detail in mappings:
        if isinstance(error, error_type):
            return HTTPException(status_code=status_code, detail=detail)
    raise error


@router.post("", response_model=ModelPromotionResponse, status_code=status.HTTP_201_CREATED)
async def create_model_promotion(
    payload: ModelPromotionCreateRequest,
    current_user: ReviewerOrAdministratorUser,
    promotion_service: TransactionalModelPromotionServiceDependency,
) -> ModelPromotionResponse:
    try:
        promotion = await promotion_service.create_promotion(
            ModelPromotionCreateInput(
                benchmark_comparison_id=payload.benchmark_comparison_id,
                selected_benchmark_result_id=payload.selected_benchmark_result_id,
                requested_by_user_id=current_user.id,
                rationale=payload.rationale,
                override_winner=payload.override_winner,
            )
        )
    except _SERVICE_ERRORS as error:
        raise _translate_error(error) from None
    return ModelPromotionResponse.model_validate(promotion)


@router.get("/{promotion_id}", response_model=ModelPromotionResponse)
async def get_model_promotion(
    promotion_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    promotion_service: ModelPromotionServiceDependency,
) -> ModelPromotionResponse:
    del current_user
    try:
        promotion = await promotion_service.get_promotion(promotion_id)
    except _SERVICE_ERRORS as error:
        raise _translate_error(error) from None
    return ModelPromotionResponse.model_validate(promotion)


@router.get("", response_model=ModelPromotionListResponse)
async def list_model_promotions(
    current_user: ReviewerOrAdministratorUser,
    promotion_service: ModelPromotionServiceDependency,
    status_filter: ModelPromotionStatus | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> ModelPromotionListResponse:
    del current_user
    items = await promotion_service.list_promotions(
        status=status_filter, offset=offset, limit=limit
    )
    return ModelPromotionListResponse(
        items=[ModelPromotionResponse.model_validate(item) for item in items],
        offset=offset,
        limit=limit,
        count=len(items),
    )


async def _review(
    promotion_id: UUID,
    payload: ModelPromotionReviewRequest,
    current_user,
    promotion_service,
    method_name: str,
) -> ModelPromotionResponse:
    try:
        promotion = await getattr(promotion_service, method_name)(
            ModelPromotionReviewInput(
                promotion_id=promotion_id,
                reviewed_by_user_id=current_user.id,
                review_note=payload.review_note,
            )
        )
    except _SERVICE_ERRORS as error:
        raise _translate_error(error) from None
    return ModelPromotionResponse.model_validate(promotion)


@router.post("/{promotion_id}/approve", response_model=ModelPromotionResponse)
async def approve_model_promotion(
    promotion_id: UUID,
    payload: ModelPromotionReviewRequest,
    current_user: AdministratorUser,
    promotion_service: TransactionalModelPromotionServiceDependency,
) -> ModelPromotionResponse:
    return await _review(promotion_id, payload, current_user, promotion_service, "approve_promotion")


@router.post("/{promotion_id}/reject", response_model=ModelPromotionResponse)
async def reject_model_promotion(
    promotion_id: UUID,
    payload: ModelPromotionReviewRequest,
    current_user: AdministratorUser,
    promotion_service: TransactionalModelPromotionServiceDependency,
) -> ModelPromotionResponse:
    return await _review(promotion_id, payload, current_user, promotion_service, "reject_promotion")


@router.post("/{promotion_id}/cancel", response_model=ModelPromotionResponse)
async def cancel_model_promotion(
    promotion_id: UUID,
    payload: ModelPromotionCancelRequest,
    current_user: ReviewerOrAdministratorUser,
    promotion_service: TransactionalModelPromotionServiceDependency,
) -> ModelPromotionResponse:
    try:
        promotion = await promotion_service.cancel_promotion(
            ModelPromotionCancelInput(
                promotion_id=promotion_id,
                cancelled_by_user_id=current_user.id,
                cancellation_note=payload.cancellation_note,
            )
        )
    except _SERVICE_ERRORS as error:
        raise _translate_error(error) from None
    return ModelPromotionResponse.model_validate(promotion)
