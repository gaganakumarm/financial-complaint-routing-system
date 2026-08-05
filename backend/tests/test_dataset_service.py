"""Dataset service tests without a database."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import DatasetSplit, DatasetVersion
from app.services import DatasetService, DatasetVersionAlreadyExistsError, DatasetVersionNotFoundError, InvalidDatasetVersionError


def repository():
    repo = MagicMock()
    repo.get_by_identity = AsyncMock(return_value=None); repo.get_by_content_hash = AsyncMock(return_value=None)
    repo.add = AsyncMock(); repo.flush = AsyncMock(); repo.refresh = AsyncMock(side_effect=lambda value: value)
    repo.get_by_id = AsyncMock(); repo.list = AsyncMock()
    repo.commit = AsyncMock(); repo.rollback = AsyncMock(); repo.begin = AsyncMock()
    return repo


def values():
    return dict(name="  Complaints  ", version=" v1 ", source_name=" Source ", source_reference=" ref ", taxonomy_version=" tax-v1 ", split=DatasetSplit.TEST, record_count=3, content_hash=" abc123 ", preparation_details={"cleaned": True})


@pytest.mark.anyio
async def test_create_normalizes_persists_and_is_transaction_neutral() -> None:
    repo = repository(); service = DatasetService(repo)
    created = await service.create_dataset_version(**values())
    persisted = repo.add.await_args.args[0]
    assert created is persisted
    assert (persisted.name, persisted.version, persisted.source_name, persisted.source_reference, persisted.taxonomy_version, persisted.content_hash) == ("Complaints", "v1", "Source", "ref", "tax-v1", "abc123")
    repo.get_by_identity.assert_awaited_once_with(name="Complaints", version="v1", split=DatasetSplit.TEST)
    repo.get_by_content_hash.assert_awaited_once_with("abc123")
    repo.flush.assert_awaited_once(); repo.refresh.assert_awaited_once_with(persisted)
    repo.commit.assert_not_awaited(); repo.rollback.assert_not_awaited(); repo.begin.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("duplicate", ["identity", "hash"])
async def test_duplicate_is_safe_before_persistence(duplicate) -> None:
    repo = repository()
    if duplicate == "identity": repo.get_by_identity.return_value = object()
    else: repo.get_by_content_hash.return_value = object()
    with pytest.raises(DatasetVersionAlreadyExistsError): await DatasetService(repo).create_dataset_version(**values())
    repo.add.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("updates", [{"name": " "}, {"record_count": 0}, {"record_count": True}, {"split": "test"}, {"preparation_details": {"bad": float("nan")}}])
async def test_invalid_data_is_generic_and_has_no_repository_access(updates) -> None:
    repo = repository(); data = values(); data.update(updates)
    with pytest.raises(InvalidDatasetVersionError, match="invalid"):
        await DatasetService(repo).create_dataset_version(**data)
    repo.get_by_identity.assert_not_awaited(); repo.add.assert_not_awaited()


@pytest.mark.anyio
async def test_reads_delegate_and_translate_missing_without_mutation() -> None:
    repo = repository(); service = DatasetService(repo); identifier = uuid4(); item = DatasetVersion(id=identifier)
    repo.get_by_id.return_value = item; repo.list.return_value = [item]
    assert await service.get_dataset_version(identifier) is item
    assert await service.list_dataset_versions(offset=2, limit=7) == [item]
    repo.list.assert_awaited_once_with(offset=2, limit=7)
    repo.get_by_id.return_value = None
    with pytest.raises(DatasetVersionNotFoundError): await service.get_dataset_version(uuid4())
    repo.add.assert_not_awaited(); repo.flush.assert_not_awaited(); repo.refresh.assert_not_awaited()
    repo.commit.assert_not_awaited(); repo.rollback.assert_not_awaited(); repo.begin.assert_not_awaited()
