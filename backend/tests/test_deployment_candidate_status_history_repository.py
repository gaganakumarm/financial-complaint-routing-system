"""Deployment-candidate status-history repository tests."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import DeploymentCandidateStatusHistory
from app.repositories import DeploymentCandidateStatusHistoryRepository


def result(*values, scalar=None):
    item = MagicMock()
    item.scalars.return_value.all.return_value = list(values)
    item.scalar_one_or_none.return_value = scalar
    return item


def test_constructor_and_export() -> None:
    session = MagicMock(); repository = DeploymentCandidateStatusHistoryRepository(session)
    assert repository.session is session
    assert repository.model_type is DeploymentCandidateStatusHistory
    import app.repositories as repositories
    assert repositories.DeploymentCandidateStatusHistoryRepository is DeploymentCandidateStatusHistoryRepository
    assert "DeploymentCandidateStatusHistoryRepository" in repositories.__all__


@pytest.mark.anyio
async def test_list_is_chronological_eager_and_empty() -> None:
    first = DeploymentCandidateStatusHistory(); session = MagicMock()
    session.execute = AsyncMock(side_effect=[result(first), result()])
    repository = DeploymentCandidateStatusHistoryRepository(session); candidate_id = uuid4()
    assert await repository.list_for_candidate(candidate_id, offset=2, limit=7) == [first]
    statement = session.execute.await_args_list[0].args[0]
    assert len(statement._with_options) == 1
    assert [item.element.name for item in statement._order_by_clauses] == ["changed_at", "id"]
    assert all(item.modifier.__name__ == "asc_op" for item in statement._order_by_clauses)
    assert await repository.list_for_candidate(candidate_id) == []


@pytest.mark.anyio
async def test_latest_is_reverse_chronological_eager_and_none() -> None:
    latest = DeploymentCandidateStatusHistory(); session = MagicMock()
    session.execute = AsyncMock(side_effect=[result(scalar=latest), result(scalar=None)])
    repository = DeploymentCandidateStatusHistoryRepository(session); candidate_id = uuid4()
    assert await repository.get_latest_for_candidate(candidate_id) is latest
    statement = session.execute.await_args_list[0].args[0]
    assert len(statement._with_options) == 1
    assert [item.element.name for item in statement._order_by_clauses] == ["changed_at", "id"]
    assert all(item.modifier.__name__ == "desc_op" for item in statement._order_by_clauses)
    assert await repository.get_latest_for_candidate(candidate_id) is None


@pytest.mark.anyio
@pytest.mark.parametrize("method,args", [
    ("list_for_candidate", ("bad",)),
    ("get_latest_for_candidate", (True,)),
    ("list_for_candidate", (uuid4(), -1, 1)),
    ("list_for_candidate", (uuid4(), 0, 0)),
    ("list_for_candidate", (uuid4(), 0, 501)),
])
async def test_invalid_arguments_perform_no_sql(method, args) -> None:
    session = MagicMock(); session.execute = AsyncMock(); repository = DeploymentCandidateStatusHistoryRepository(session)
    with pytest.raises(ValueError):
        if len(args) == 1:
            await getattr(repository, method)(*args)
        else:
            await getattr(repository, method)(args[0], offset=args[1], limit=args[2])
    session.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_add_is_transaction_neutral() -> None:
    session = MagicMock(); session.commit = AsyncMock(); session.rollback = AsyncMock(); session.begin = MagicMock()
    repository = DeploymentCandidateStatusHistoryRepository(session); history = DeploymentCandidateStatusHistory()
    assert await repository.add_history(history) is history
    session.add.assert_called_once_with(history)
    session.commit.assert_not_awaited(); session.rollback.assert_not_awaited(); session.begin.assert_not_called()
    with pytest.raises(ValueError): await repository.add_history(object())
