"""Dataset example schema and route tests."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
import httpx
from pydantic import ValidationError
from app.api.routes.dataset_examples import create_dataset_examples, list_dataset_examples
from app.models import ComplaintUrgency, DatasetExample, Role, User
from app.api.dependencies import get_current_active_user, get_dataset_example_service, get_transactional_dataset_example_service
from app.schemas import DatasetExampleBatchCreateRequest, DatasetExampleResponse
from app.services import DatasetExampleAlreadyExistsError, DatasetExamplePersistenceError, DatasetExampleReferenceError, DatasetVersionNotFoundForExampleError, InvalidDatasetExampleError
from app.core.config import Settings
from app.main import create_app


def payload():
    return DatasetExampleBatchCreateRequest(examples=[{"example_id": " one ", "title": " title ", "description": " detail ", "expected_category_id": uuid4(), "expected_department_id": uuid4(), "expected_urgency": "high"}])


def row(dataset_id):
    item = payload().examples[0]
    return DatasetExample(id=uuid4(), dataset_version_id=dataset_id, **item.model_dump(), created_at=datetime.now(timezone.utc))


def test_schema_normalizes_and_rejects_duplicates() -> None:
    assert payload().examples[0].example_id == "one"
    with pytest.raises(ValidationError): DatasetExampleBatchCreateRequest(examples=[payload().examples[0], payload().examples[0]])


@pytest.mark.anyio
async def test_create_and_list_delegate_exact_values() -> None:
    identifier = uuid4(); service = MagicMock(); service.create_examples = AsyncMock(return_value=[row(identifier)]); service.list_examples = AsyncMock(return_value=[row(identifier)])
    created = await create_dataset_examples(identifier, payload(), User(id=uuid4()), service)
    assert created.count == 1 and created.items[0].dataset_version_id == identifier
    assert service.create_examples.await_args.kwargs["dataset_version_id"] == identifier
    listed = await list_dataset_examples(identifier, User(id=uuid4()), service, 2, 8)
    assert (listed.offset, listed.limit, listed.count) == (2, 8, 1)
    service.list_examples.assert_awaited_once_with(dataset_version_id=identifier, offset=2, limit=8)


@pytest.mark.parametrize("update", [
    {"example_id": " "}, {"title": " "}, {"description": " "},
    {"title": "x" * 201}, {"description": "x" * 10001},
    {"expected_category_id": "bad"}, {"expected_department_id": "bad"},
    {"expected_urgency": "urgent"}, {"extra": "forbidden"},
])
def test_item_schema_rejects_invalid_fields(update) -> None:
    data = payload().examples[0].model_dump(); data.update(update)
    with pytest.raises(ValidationError): DatasetExampleBatchCreateRequest(examples=[data])


def test_batch_schema_rejects_empty_oversized_and_duplicate_batches() -> None:
    item = payload().examples[0]
    for items in ([], [item] * 501, [item, item]):
        with pytest.raises(ValidationError): DatasetExampleBatchCreateRequest(examples=items)


def test_response_schema_is_safe() -> None:
    response = DatasetExampleResponse.model_validate(row(uuid4())).model_dump()
    assert set(response) == {"id", "dataset_version_id", "example_id", "title", "description", "expected_category_id", "expected_department_id", "expected_urgency", "created_at"}
    assert not {"dataset_version", "expected_category", "expected_department", "_sa_instance_state"} & response.keys()


@pytest.mark.anyio
@pytest.mark.parametrize("error,status_code,detail", [
    (DatasetVersionNotFoundForExampleError("secret"), 404, "Dataset version not found"),
    (DatasetExampleAlreadyExistsError("secret"), 409, "Dataset example already exists"),
    (DatasetExampleReferenceError("secret"), 422, "Invalid dataset example reference"),
    (InvalidDatasetExampleError("secret"), 422, "Invalid dataset example"),
    (DatasetExamplePersistenceError("database secret"), 500, "Dataset example persistence failed"),
])
async def test_create_maps_known_failures_without_leaking(error, status_code, detail) -> None:
    service = MagicMock(); service.create_examples = AsyncMock(side_effect=error)
    with pytest.raises(Exception) as caught:
        await create_dataset_examples(uuid4(), payload(), User(id=uuid4()), service)
    assert (caught.value.status_code, caught.value.detail) == (status_code, detail)
    assert "secret" not in str(caught.value)


@pytest.mark.anyio
async def test_unrelated_create_failure_propagates() -> None:
    service = MagicMock(); failure = RuntimeError("unrelated"); service.create_examples = AsyncMock(side_effect=failure)
    with pytest.raises(RuntimeError) as caught:
        await create_dataset_examples(uuid4(), payload(), User(id=uuid4()), service)
    assert caught.value is failure


def test_openapi_contract_is_safe_and_nonconflicting() -> None:
    schema = create_app(Settings()).openapi(); path = schema["paths"]["/api/datasets/{dataset_version_id}/examples"]
    assert set(path) == {"post", "get"}
    assert path["post"]["tags"] == ["Dataset Examples"] and path["get"]["tags"] == ["Dataset Examples"]
    assert path["post"]["security"] == [{"OAuth2PasswordBearer": []}]
    assert path["get"]["security"] == [{"OAuth2PasswordBearer": []}]
    paths = list(schema["paths"])
    assert len(paths) == len(set(paths))
    assert not any("csv" in value or "upload" in value for value in paths)
    assert "/api/datasets/{dataset_version_id}" in paths


def role_user(name: str) -> User:
    role = Role(id=uuid4(), name=name, display_name=name.title(), is_active=True)
    return User(id=uuid4(), role_id=role.id, role=role, email=f"{name}@example.com", password_hash="hash", full_name=name.title(), is_active=True)


@pytest.mark.anyio
@pytest.mark.parametrize("role,method,expected", [
    ("administrator", "post", 201), ("reviewer", "post", 403), ("customer", "post", 403),
    ("administrator", "get", 200), ("reviewer", "get", 200), ("customer", "get", 403),
])
async def test_role_authorization_through_fastapi(role, method, expected) -> None:
    identifier = uuid4(); application = create_app(Settings()); mocked = MagicMock()
    mocked.create_examples = AsyncMock(return_value=[row(identifier)]); mocked.list_examples = AsyncMock(return_value=[row(identifier)])
    application.dependency_overrides[get_current_active_user] = lambda: role_user(role)
    application.dependency_overrides[get_dataset_example_service] = lambda: mocked
    application.dependency_overrides[get_transactional_dataset_example_service] = lambda: mocked
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        response = await client.request(method, f"/api/datasets/{identifier}/examples", json=payload().model_dump(mode="json") if method == "post" else None)
    assert response.status_code == expected


@pytest.mark.anyio
@pytest.mark.parametrize("method", ["post", "get"])
async def test_unauthenticated_requests_are_401(method) -> None:
    application = create_app(Settings()); identifier = uuid4()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        response = await client.request(method, f"/api/datasets/{identifier}/examples", json=payload().model_dump(mode="json") if method == "post" else None)
    assert response.status_code == 401
