"""Benchmark experiment and result REST API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import (
    BenchmarkServiceDependency,
    TransactionalBenchmarkExperimentRepositoryDependency,
    TransactionalDatasetVersionRepositoryDependency,
)
from app.authz import AdministratorUser, ReviewerOrAdministratorUser
from app.models import BenchmarkExperiment, BenchmarkExperimentStatus
from app.schemas import (
    BenchmarkExperimentCreateRequest,
    BenchmarkExperimentListResponse,
    BenchmarkExperimentResponse,
    BenchmarkResultListResponse,
    BenchmarkResultResponse,
)
from app.services import BenchmarkExperimentNotFoundError, BenchmarkResultNotFoundError


router = APIRouter(prefix="/benchmarks", tags=["Benchmarks"])


@router.post(
    "/experiments",
    response_model=BenchmarkExperimentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_benchmark_experiment(
    payload: BenchmarkExperimentCreateRequest,
    current_user: AdministratorUser,
    dataset_repository: TransactionalDatasetVersionRepositoryDependency,
    experiment_repository: TransactionalBenchmarkExperimentRepositoryDependency,
) -> BenchmarkExperimentResponse:
    del current_user
    if await dataset_repository.get_by_id(payload.dataset_version_id) is None:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    experiment = BenchmarkExperiment(
        dataset_version_id=payload.dataset_version_id,
        name=payload.name,
        status=BenchmarkExperimentStatus.PENDING,
        configuration=payload.configuration,
        started_at=None,
        completed_at=None,
        failure_message=None,
    )
    await experiment_repository.add(experiment)
    await experiment_repository.flush()
    experiment = await experiment_repository.refresh(experiment)
    return BenchmarkExperimentResponse.model_validate(experiment)


@router.get(
    "/datasets/{dataset_version_id}/experiments",
    response_model=BenchmarkExperimentListResponse,
)
async def list_dataset_experiments(
    dataset_version_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    benchmark_service: BenchmarkServiceDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> BenchmarkExperimentListResponse:
    del current_user
    items = await benchmark_service.list_dataset_experiments(
        dataset_version_id=dataset_version_id, offset=offset, limit=limit
    )
    return BenchmarkExperimentListResponse(
        items=[BenchmarkExperimentResponse.model_validate(item) for item in items],
        offset=offset,
        limit=limit,
        count=len(items),
    )


@router.get(
    "/experiments/{experiment_id}/results",
    response_model=BenchmarkResultListResponse,
)
async def list_experiment_results(
    experiment_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    benchmark_service: BenchmarkServiceDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> BenchmarkResultListResponse:
    del current_user
    items = await benchmark_service.list_experiment_results(
        experiment_id=experiment_id, offset=offset, limit=limit
    )
    return BenchmarkResultListResponse(
        items=[BenchmarkResultResponse.model_validate(item) for item in items],
        offset=offset,
        limit=limit,
        count=len(items),
    )


@router.get(
    "/experiments/{experiment_id}", response_model=BenchmarkExperimentResponse
)
async def get_benchmark_experiment(
    experiment_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    benchmark_service: BenchmarkServiceDependency,
) -> BenchmarkExperimentResponse:
    del current_user
    try:
        experiment = await benchmark_service.get_experiment(experiment_id)
    except BenchmarkExperimentNotFoundError:
        raise HTTPException(
            status_code=404, detail="Benchmark experiment not found"
        ) from None
    return BenchmarkExperimentResponse.model_validate(experiment)


@router.get("/results/{result_id}", response_model=BenchmarkResultResponse)
async def get_benchmark_result(
    result_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    benchmark_service: BenchmarkServiceDependency,
) -> BenchmarkResultResponse:
    del current_user
    try:
        result = await benchmark_service.get_result(result_id)
    except BenchmarkResultNotFoundError:
        raise HTTPException(status_code=404, detail="Benchmark result not found") from None
    return BenchmarkResultResponse.model_validate(result)
