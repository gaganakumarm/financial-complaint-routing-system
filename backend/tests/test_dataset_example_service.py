"""Dataset example service tests."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from app.models import ComplaintUrgency
from app.services import DatasetExampleAlreadyExistsError, DatasetExampleInput, DatasetExampleNotFoundError, DatasetExamplePersistenceError, DatasetExampleReferenceError, DatasetExampleService, DatasetVersionNotFoundForExampleError, InvalidDatasetExampleError


def dependencies():
    dataset, examples, categories, departments = (MagicMock() for _ in range(4))
    dataset.get_by_id = AsyncMock(return_value=object()); examples.example_ids_exist = AsyncMock(return_value=set()); examples.add = AsyncMock(); examples.flush = AsyncMock(); examples.refresh = AsyncMock(side_effect=lambda row: row); examples.list_for_dataset = AsyncMock(return_value=[])
    categories.get_by_ids = AsyncMock(side_effect=lambda ids: {identifier: SimpleNamespace(id=identifier, is_active=True) for identifier in ids})
    departments.get_by_ids = AsyncMock(side_effect=lambda ids: {identifier: SimpleNamespace(id=identifier, is_active=True) for identifier in ids})
    return dataset, examples, categories, departments


def service(parts):
    d, e, c, p = parts
    return DatasetExampleService(dataset_version_repository=d, dataset_example_repository=e, complaint_category_repository=c, department_repository=p)


def input(example_id="one"):
    return DatasetExampleInput(example_id, " Title ", " Description ", uuid4(), uuid4(), ComplaintUrgency.HIGH)


@pytest.mark.anyio
async def test_valid_batch_is_fully_validated_then_persisted_in_order() -> None:
    parts = dependencies(); rows = await service(parts).create_examples(dataset_version_id=uuid4(), examples=[input("one"), input("two")])
    assert [row.example_id for row in rows] == ["one", "two"]
    assert parts[1].add.await_count == 2
    parts[1].flush.assert_awaited_once(); assert parts[1].refresh.await_count == 2


@pytest.mark.anyio
async def test_duplicate_and_invalid_reference_prevent_all_adds() -> None:
    parts = dependencies()
    with pytest.raises(InvalidDatasetExampleError): await service(parts).create_examples(dataset_version_id=uuid4(), examples=[input("same"), input("same")])
    parts[1].add.assert_not_awaited()
    parts = dependencies(); parts[2].get_by_ids.side_effect = None; parts[2].get_by_ids.return_value = {}
    with pytest.raises(DatasetExampleReferenceError): await service(parts).create_examples(dataset_version_id=uuid4(), examples=[input()])
    parts[1].add.assert_not_awaited()
    parts = dependencies(); parts[1].example_ids_exist.return_value = {"one"}
    with pytest.raises(DatasetExampleAlreadyExistsError): await service(parts).create_examples(dataset_version_id=uuid4(), examples=[input()])
    parts[1].add.assert_not_awaited()


@pytest.mark.anyio
async def test_list_is_read_only_and_delegates_pagination() -> None:
    parts = dependencies(); identifier = uuid4()
    assert await service(parts).list_examples(dataset_version_id=identifier, offset=3, limit=7) == []
    parts[1].list_for_dataset.assert_awaited_once_with(identifier, offset=3, limit=7)
    parts[1].add.assert_not_awaited(); parts[1].flush.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("examples", [[], "not-a-batch", b"not-a-batch", [object()]])
async def test_invalid_batch_shape_never_adds(examples) -> None:
    parts = dependencies()
    with pytest.raises(InvalidDatasetExampleError):
        await service(parts).create_examples(dataset_version_id=uuid4(), examples=examples)
    parts[1].add.assert_not_awaited()


@pytest.mark.anyio
async def test_missing_dataset_and_invalid_dataset_uuid_are_safe() -> None:
    parts = dependencies(); parts[0].get_by_id.return_value = None
    with pytest.raises(DatasetVersionNotFoundForExampleError):
        await service(parts).create_examples(dataset_version_id=uuid4(), examples=[input()])
    with pytest.raises(InvalidDatasetExampleError):
        await service(parts).create_examples(dataset_version_id="bad", examples=[input()])
    parts[1].add.assert_not_awaited()


@pytest.mark.anyio
async def test_reference_queries_are_deduplicated_and_batched() -> None:
    parts = dependencies(); category_id, department_id = uuid4(), uuid4()
    items = [DatasetExampleInput(str(index), "title", "description", category_id, department_id, ComplaintUrgency.LOW) for index in range(500)]
    await service(parts).create_examples(dataset_version_id=uuid4(), examples=items)
    parts[2].get_by_ids.assert_awaited_once_with({category_id})
    parts[3].get_by_ids.assert_awaited_once_with({department_id})
    parts[1].example_ids_exist.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("field,value", [("example_id", " "), ("title", " "), ("title", "x" * 201), ("description", " "), ("description", "x" * 10001), ("expected_category_id", "bad"), ("expected_department_id", "bad"), ("expected_urgency", "high")])
async def test_item_validation_is_complete_before_add(field, value) -> None:
    parts = dependencies(); data = input().__dict__ if hasattr(input(), "__dict__") else {name: getattr(input(), name) for name in DatasetExampleInput.__dataclass_fields__}
    data[field] = value
    with pytest.raises(InvalidDatasetExampleError):
        await service(parts).create_examples(dataset_version_id=uuid4(), examples=[DatasetExampleInput(**data)])
    parts[1].add.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["add", "flush", "refresh"])
async def test_persistence_failures_are_generic_and_transaction_neutral(operation) -> None:
    parts = dependencies(); getattr(parts[1], operation).side_effect = RuntimeError("database title secret")
    with pytest.raises(DatasetExamplePersistenceError) as caught:
        await service(parts).create_examples(dataset_version_id=uuid4(), examples=[input()])
    assert str(caught.value) == "Dataset example persistence failed."
    for method in ("commit", "rollback", "begin"):
        getattr(parts[1], method).assert_not_called()


@pytest.mark.anyio
async def test_cancellation_propagates() -> None:
    import asyncio
    parts = dependencies(); parts[1].flush.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await service(parts).create_examples(dataset_version_id=uuid4(), examples=[input()])


@pytest.mark.anyio
async def test_get_example_found_and_missing() -> None:
    parts = dependencies(); identifier = uuid4(); found = object()
    parts[1].get_for_dataset_and_example_id = AsyncMock(return_value=found)
    assert await service(parts).get_example(dataset_version_id=identifier, example_id=" one ") is found
    parts[1].get_for_dataset_and_example_id.return_value = None
    with pytest.raises(DatasetExampleNotFoundError):
        await service(parts).get_example(dataset_version_id=identifier, example_id="missing")


@pytest.mark.anyio
async def test_ingestion_does_not_mutate_immutable_dataset_record_count() -> None:
    parts = dependencies(); dataset = SimpleNamespace(record_count=37); parts[0].get_by_id.return_value = dataset
    await service(parts).create_examples(dataset_version_id=uuid4(), examples=[input()])
    assert dataset.record_count == 37
    parts[0].add.assert_not_called(); parts[0].flush.assert_not_called(); parts[0].refresh.assert_not_called()
