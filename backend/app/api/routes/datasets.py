"""Dataset-version metadata REST API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import DatasetServiceDependency, TransactionalDatasetServiceDependency
from app.authz import AdministratorUser, ReviewerOrAdministratorUser
from app.schemas import DatasetVersionCreateRequest, DatasetVersionListResponse, DatasetVersionResponse
from app.services import (
    DatasetVersionAlreadyExistsError,
    DatasetVersionNotFoundError,
    InvalidDatasetVersionError,
)


router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.post("", response_model=DatasetVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset_version(
    payload: DatasetVersionCreateRequest,
    current_user: AdministratorUser,
    dataset_service: TransactionalDatasetServiceDependency,
) -> DatasetVersionResponse:
    del current_user
    try:
        dataset = await dataset_service.create_dataset_version(**payload.model_dump())
    except DatasetVersionAlreadyExistsError:
        raise HTTPException(status_code=409, detail="Dataset version already exists") from None
    except InvalidDatasetVersionError:
        raise HTTPException(status_code=422, detail="Invalid dataset version data") from None
    return DatasetVersionResponse.model_validate(dataset)


@router.get("", response_model=DatasetVersionListResponse)
async def list_dataset_versions(
    current_user: ReviewerOrAdministratorUser,
    dataset_service: DatasetServiceDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> DatasetVersionListResponse:
    del current_user
    items = await dataset_service.list_dataset_versions(offset=offset, limit=limit)
    return DatasetVersionListResponse(
        items=[DatasetVersionResponse.model_validate(item) for item in items],
        offset=offset,
        limit=limit,
        count=len(items),
    )


@router.get("/{dataset_version_id}", response_model=DatasetVersionResponse)
async def get_dataset_version(
    dataset_version_id: UUID,
    current_user: ReviewerOrAdministratorUser,
    dataset_service: DatasetServiceDependency,
) -> DatasetVersionResponse:
    del current_user
    try:
        dataset = await dataset_service.get_dataset_version(dataset_version_id)
    except DatasetVersionNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset version not found") from None
    return DatasetVersionResponse.model_validate(dataset)
