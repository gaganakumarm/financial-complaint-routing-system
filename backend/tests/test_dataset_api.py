"""Dataset-version API tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from pydantic import ValidationError
import pytest

from app.api.dependencies import get_dataset_service, get_transactional_dataset_service
from app.api.routes.datasets import create_dataset_version, get_dataset_version, list_dataset_versions
from app.core.config import Settings
from app.main import create_app
from app.models import DatasetSplit, DatasetVersion, User
from app.schemas import DatasetVersionCreateRequest, DatasetVersionResponse
from app.services import DatasetVersionAlreadyExistsError, DatasetVersionNotFoundError


def item(**updates):
    values = dict(id=uuid4(), name="Complaints", version="v1", source_name="Source", source_reference=None, taxonomy_version="tax-v1", split=DatasetSplit.TEST, record_count=2, content_hash="abc", preparation_details=None, created_at=datetime.now(timezone.utc)); values.update(updates); return DatasetVersion(**values)


def payload():
    return DatasetVersionCreateRequest(name=" Complaints ", version=" v1 ", source_name=" Source ", source_reference=None, taxonomy_version=" tax-v1 ", split=DatasetSplit.TEST, record_count=2, content_hash=" abc ")


def test_schema_uses_exact_fields_and_forbids_invalid_data() -> None:
    request = payload(); assert (request.name, request.version, request.content_hash) == ("Complaints", "v1", "abc")
    assert set(request.model_dump()) == {"name", "version", "source_name", "source_reference", "taxonomy_version", "split", "record_count", "content_hash", "preparation_details"}
    for data in [{**request.model_dump(), "status": "active"}, {**request.model_dump(), "record_count": 0}, {**request.model_dump(), "name": " "}]:
        with pytest.raises(ValidationError): DatasetVersionCreateRequest(**data)
    assert "benchmark_experiments" not in DatasetVersionResponse.model_validate(item()).model_dump()


@pytest.mark.anyio
async def test_create_delegates_exact_values_and_maps_duplicate() -> None:
    service = MagicMock(); service.create_dataset_version = AsyncMock(return_value=item())
    response = await create_dataset_version(payload(), User(id=uuid4()), service)
    assert response.name == "Complaints"
    service.create_dataset_version.assert_awaited_once_with(**payload().model_dump())
    service.create_dataset_version.side_effect = DatasetVersionAlreadyExistsError("secret")
    with pytest.raises(Exception) as caught: await create_dataset_version(payload(), User(id=uuid4()), service)
    assert (caught.value.status_code, caught.value.detail) == (409, "Dataset version already exists")


@pytest.mark.anyio
async def test_read_routes_are_safe_and_delegate_pagination() -> None:
    dataset = item(); user = User(id=uuid4()); service = MagicMock()
    service.get_dataset_version = AsyncMock(return_value=dataset); service.list_dataset_versions = AsyncMock(return_value=[dataset])
    assert (await get_dataset_version(dataset.id, user, service)).id == dataset.id
    listed = await list_dataset_versions(user, service, 4, 9)
    assert (listed.offset, listed.limit, listed.count) == (4, 9, 1)
    service.list_dataset_versions.assert_awaited_once_with(offset=4, limit=9)
    service.get_dataset_version.side_effect = DatasetVersionNotFoundError("secret")
    with pytest.raises(Exception) as caught: await get_dataset_version(uuid4(), user, service)
    assert (caught.value.status_code, caught.value.detail) == (404, "Dataset version not found")


def test_dependency_construction_is_exact_and_neutral() -> None:
    read_repo, write_repo = MagicMock(), MagicMock()
    read = get_dataset_service(read_repo); write = get_transactional_dataset_service(write_repo)
    assert read._repository is read_repo and write._repository is write_repo
    assert read_repo.mock_calls == [] and write_repo.mock_calls == []


def test_openapi_has_only_metadata_dataset_routes() -> None:
    schema = create_app(Settings()).openapi(); paths = schema["paths"]
    assert set(paths["/api/datasets"]) >= {"post", "get"}
    assert "get" in paths["/api/datasets/{dataset_version_id}"]
    assert not any("upload" in path or "rows" in path or "examples" in path for path in paths if "dataset" in path)
    properties = schema["components"]["schemas"]["DatasetVersionResponse"]["properties"]
    assert set(properties) == {"id", "name", "version", "source_name", "source_reference", "taxonomy_version", "split", "record_count", "content_hash", "preparation_details", "created_at"}
