"""Benchmark comparison REST API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import (
    BenchmarkComparisonServiceDependency,
    TransactionalBenchmarkComparisonServiceDependency,
)
from app.authz import ReviewerOrAdministratorUser
from app.schemas import (
    BenchmarkComparisonCreateRequest,
    BenchmarkComparisonListResponse,
    BenchmarkComparisonResponse,
)
from app.services import (
    BenchmarkComparisonInput,
    BenchmarkComparisonNotFoundError,
    BenchmarkComparisonPersistenceError,
    BenchmarkResultNotFoundForComparisonError,
    IncompleteBenchmarkResultError,
    IncompatibleBenchmarkDatasetError,
    InvalidBenchmarkComparisonError,
    MissingBenchmarkMetricsError,
)


router = APIRouter(prefix="/benchmark-comparisons", tags=["Benchmark Comparisons"])


def _translate_error(error: Exception) -> HTTPException:
    mappings = (
        (BenchmarkComparisonNotFoundError, 404, "Benchmark comparison not found"),
        (BenchmarkResultNotFoundForComparisonError, 404, "Benchmark result not found"),
        (InvalidBenchmarkComparisonError, 422, "Invalid benchmark comparison"),
        (IncompleteBenchmarkResultError, 409, "Benchmark result is not complete"),
        (MissingBenchmarkMetricsError, 409, "Benchmark result metrics are incomplete"),
        (IncompatibleBenchmarkDatasetError, 409, "Benchmark results use incompatible datasets"),
        (BenchmarkComparisonPersistenceError, 500, "Benchmark comparison could not be persisted"),
    )
    for error_type, status_code, detail in mappings:
        if isinstance(error, error_type):
            return HTTPException(status_code=status_code, detail=detail)
    raise error


@router.post("", response_model=BenchmarkComparisonResponse, status_code=status.HTTP_201_CREATED)
async def create_benchmark_comparison(
    payload: BenchmarkComparisonCreateRequest,
    current_user: ReviewerOrAdministratorUser,
    comparison_service: TransactionalBenchmarkComparisonServiceDependency,
) -> BenchmarkComparisonResponse:
    try:
        comparison = await comparison_service.create_comparison(
            BenchmarkComparisonInput(
                benchmark_result_ids=payload.benchmark_result_ids,
                created_by_user_id=current_user.id,
                ranking_metric=payload.ranking_metric,
            )
        )
    except (
        BenchmarkResultNotFoundForComparisonError,
        InvalidBenchmarkComparisonError,
        IncompleteBenchmarkResultError,
        MissingBenchmarkMetricsError,
        IncompatibleBenchmarkDatasetError,
        BenchmarkComparisonPersistenceError,
    ) as error:
        raise _translate_error(error) from None
    return BenchmarkComparisonResponse.model_validate(comparison)


@router.get("/{comparison_id}", response_model=BenchmarkComparisonResponse)
async def get_benchmark_comparison(
    comparison_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    comparison_service: BenchmarkComparisonServiceDependency,
) -> BenchmarkComparisonResponse:
    del current_user
    try:
        comparison = await comparison_service.get_comparison(comparison_id)
    except BenchmarkComparisonNotFoundError as error:
        raise _translate_error(error) from None
    return BenchmarkComparisonResponse.model_validate(comparison)


@router.get("", response_model=BenchmarkComparisonListResponse)
async def list_benchmark_comparisons(
    current_user: ReviewerOrAdministratorUser,
    comparison_service: BenchmarkComparisonServiceDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> BenchmarkComparisonListResponse:
    del current_user
    items = await comparison_service.list_comparisons(offset=offset, limit=limit)
    return BenchmarkComparisonListResponse(
        items=[BenchmarkComparisonResponse.model_validate(item) for item in items],
        offset=offset,
        limit=limit,
        count=len(items),
    )
