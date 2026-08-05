"""Deployment candidate repository tests."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from app.models import DeploymentCandidate, DeploymentCandidateStatus
from app.repositories import DeploymentCandidateRepository


def result(*values, scalar=None):
    item = MagicMock(); item.scalar_one_or_none.return_value = scalar; item.scalars.return_value.all.return_value = list(values); return item


def test_constructor() -> None:
    session = MagicMock(); repository = DeploymentCandidateRepository(session)
    assert repository.session is session and repository.model_type is DeploymentCandidate


@pytest.mark.anyio
async def test_get_methods_validate_and_missing_returns_none() -> None:
    session = MagicMock(); session.get = AsyncMock(return_value=None); session.execute = AsyncMock(return_value=result(scalar=None)); repository = DeploymentCandidateRepository(session); identifier = uuid4()
    assert await repository.get_by_id(identifier) is None
    assert await repository.get_with_details(identifier) is None
    assert await repository.get_for_promotion(identifier) is None
    for method in (repository.get_by_id, repository.get_with_details, repository.get_for_promotion):
        with pytest.raises(ValueError): await method("bad")


@pytest.mark.anyio
async def test_detail_and_active_queries_eager_load_complete_graph() -> None:
    candidate = object(); session = MagicMock(); session.execute = AsyncMock(side_effect=[result(scalar=candidate), result(scalar=candidate)]); repository = DeploymentCandidateRepository(session)
    assert await repository.get_with_details(uuid4()) is candidate
    assert len(session.execute.await_args_list[0].args[0]._with_options) == 5
    assert await repository.get_active_candidate() is candidate
    active_statement = session.execute.await_args_list[1].args[0]
    assert len(active_statement._with_options) == 5 and DeploymentCandidateStatus.ACTIVE in active_statement.compile().params.values()


@pytest.mark.anyio
async def test_list_filter_order_pagination_and_empty() -> None:
    first = SimpleNamespace(id=uuid4()); session = MagicMock(); session.execute = AsyncMock(return_value=result(first)); repository = DeploymentCandidateRepository(session)
    assert await repository.list_candidates(status=DeploymentCandidateStatus.STAGED, offset=2, limit=7) == [first]
    statement = session.execute.await_args.args[0]
    assert len(statement._order_by_clauses) == 2 and len(statement._with_options) == 5
    assert DeploymentCandidateStatus.STAGED in statement.compile().params.values()
    session.execute.return_value = result(); assert await repository.list_candidates() == []
    with pytest.raises(ValueError): await repository.list_candidates(status="staged")
    for offset, limit in ((-1, 1), (0, 0), (0, 501)):
        with pytest.raises(ValueError): await repository.list_candidates(offset=offset, limit=limit)


@pytest.mark.anyio
async def test_add_flush_refresh_are_transaction_neutral() -> None:
    session = MagicMock(); session.flush = AsyncMock(); session.refresh = AsyncMock(); session.commit = AsyncMock(); session.rollback = AsyncMock(); session.begin = MagicMock()
    repository = DeploymentCandidateRepository(session); candidate = DeploymentCandidate()
    assert await repository.add_candidate(candidate) is candidate
    await repository.flush(); assert await repository.refresh(candidate) is candidate
    session.add.assert_called_once_with(candidate); session.flush.assert_awaited_once(); session.refresh.assert_awaited_once_with(candidate)
    session.commit.assert_not_awaited(); session.rollback.assert_not_awaited(); session.begin.assert_not_called()


def test_repository_export() -> None:
    import app.repositories as repositories
    assert repositories.DeploymentCandidateRepository is DeploymentCandidateRepository
    assert "DeploymentCandidateRepository" in repositories.__all__
