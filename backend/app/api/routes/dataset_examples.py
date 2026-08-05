"""Dataset example ingestion and listing routes."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import DatasetExampleServiceDependency, TransactionalDatasetExampleServiceDependency
from app.authz import AdministratorUser, ReviewerOrAdministratorUser
from app.schemas import DatasetExampleBatchCreateRequest, DatasetExampleBatchCreateResponse, DatasetExampleListResponse, DatasetExampleResponse
from app.services import DatasetExampleAlreadyExistsError, DatasetExampleInput, DatasetExamplePersistenceError, DatasetExampleReferenceError, DatasetVersionNotFoundForExampleError, InvalidDatasetExampleError

router = APIRouter(prefix="/datasets", tags=["Dataset Examples"])


@router.post("/{dataset_version_id}/examples", response_model=DatasetExampleBatchCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_dataset_examples(dataset_version_id: UUID, payload: DatasetExampleBatchCreateRequest, current_user: AdministratorUser, service: TransactionalDatasetExampleServiceDependency) -> DatasetExampleBatchCreateResponse:
    del current_user
    inputs = [DatasetExampleInput(**item.model_dump()) for item in payload.examples]
    try:
        rows = await service.create_examples(dataset_version_id=dataset_version_id, examples=inputs)
    except DatasetVersionNotFoundForExampleError:
        raise HTTPException(404, "Dataset version not found") from None
    except DatasetExampleAlreadyExistsError:
        raise HTTPException(409, "Dataset example already exists") from None
    except DatasetExampleReferenceError:
        raise HTTPException(422, "Invalid dataset example reference") from None
    except InvalidDatasetExampleError:
        raise HTTPException(422, "Invalid dataset example") from None
    except DatasetExamplePersistenceError:
        raise HTTPException(500, "Dataset example persistence failed") from None
    items = [DatasetExampleResponse.model_validate(row) for row in rows]
    return DatasetExampleBatchCreateResponse(items=items, count=len(items))


@router.get("/{dataset_version_id}/examples", response_model=DatasetExampleListResponse)
async def list_dataset_examples(dataset_version_id: UUID, current_user: ReviewerOrAdministratorUser, service: DatasetExampleServiceDependency, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)) -> DatasetExampleListResponse:
    del current_user
    try:
        rows = await service.list_examples(dataset_version_id=dataset_version_id, offset=offset, limit=limit)
    except DatasetVersionNotFoundForExampleError:
        raise HTTPException(404, "Dataset version not found") from None
    items = [DatasetExampleResponse.model_validate(row) for row in rows]
    return DatasetExampleListResponse(items=items, offset=offset, limit=limit, count=len(items))
