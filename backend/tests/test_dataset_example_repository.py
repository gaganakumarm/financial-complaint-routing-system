"""Dataset example repository tests."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from app.models import DatasetExample
from app.repositories import ComplaintCategoryRepository, DatasetExampleRepository, DepartmentRepository


def test_repository_constructor_and_validation() -> None:
    session = MagicMock(); repository = DatasetExampleRepository(session)
    assert repository.session is session and repository.model_type is DatasetExample
    with pytest.raises(ValueError): repository._validate_pagination(-1, 10)
    with pytest.raises(ValueError): repository._validate_pagination(0, 501)


@pytest.mark.anyio
async def test_empty_existing_id_lookup_performs_no_sql() -> None:
    session = MagicMock(); session.execute = AsyncMock(); repository = DatasetExampleRepository(session)
    assert await repository.example_ids_exist(dataset_version_id=uuid4(), example_ids=[]) == set()
    session.execute.assert_not_called()


@pytest.mark.anyio
async def test_uuid_and_example_id_are_validated() -> None:
    repository = DatasetExampleRepository(MagicMock())
    with pytest.raises(ValueError): await repository.list_for_dataset("bad")
    with pytest.raises(ValueError): await repository.get_for_dataset_and_example_id(dataset_version_id=uuid4(), example_id=" ")


def result(*values, scalar=None):
    result = MagicMock(); result.scalar_one_or_none.return_value = scalar
    result.scalar_one.return_value = scalar
    result.scalars.return_value.all.return_value = list(values)
    return result


@pytest.mark.anyio
async def test_get_normalizes_and_missing_returns_none() -> None:
    session = MagicMock(); session.execute = AsyncMock(return_value=result(scalar=None)); repository = DatasetExampleRepository(session); identifier = uuid4()
    assert await repository.get_for_dataset_and_example_id(dataset_version_id=identifier, example_id=" one ") is None
    statement = session.execute.await_args.args[0]
    assert "dataset_examples.example_id = :example_id_1" in str(statement)
    assert statement.compile().params["example_id_1"] == "one"


@pytest.mark.anyio
async def test_list_count_and_existing_ids_use_exact_dataset() -> None:
    first, second, identifier = DatasetExample(), DatasetExample(), uuid4()
    session = MagicMock(); session.execute = AsyncMock(side_effect=[result(first, second), result(scalar=2), result("one", "two")]); repository = DatasetExampleRepository(session)
    assert await repository.list_for_dataset(identifier, offset=3, limit=7) == [first, second]
    list_statement = session.execute.await_args_list[0].args[0]
    assert list_statement.compile().params["dataset_version_id_1"] == identifier
    assert len(list_statement._order_by_clauses) == 2
    assert await repository.count_for_dataset(identifier) == 2
    assert await repository.example_ids_exist(dataset_version_id=identifier, example_ids=[" one ", "two", "one"]) == {"one", "two"}
    assert session.execute.await_count == 3


@pytest.mark.anyio
@pytest.mark.parametrize("offset,limit", [(-1, 1), (0, 0), (0, 501)])
async def test_list_rejects_invalid_pagination_without_sql(offset, limit) -> None:
    session = MagicMock(); session.execute = AsyncMock(); repository = DatasetExampleRepository(session)
    with pytest.raises(ValueError): await repository.list_for_dataset(uuid4(), offset=offset, limit=limit)
    session.execute.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("repository_type", [ComplaintCategoryRepository, DepartmentRepository])
async def test_reference_repository_batches_ids_and_skips_empty(repository_type) -> None:
    identifier = uuid4(); entity = SimpleNamespace(id=identifier)
    session = MagicMock(); session.execute = AsyncMock(return_value=result(entity)); repository = repository_type(session)
    assert await repository.get_by_ids([identifier, identifier]) == {identifier: entity}
    session.execute.assert_awaited_once()
    session.execute.reset_mock()
    assert await repository.get_by_ids([]) == {}
    session.execute.assert_not_awaited()
    with pytest.raises(ValueError): await repository.get_by_ids(["bad"])
