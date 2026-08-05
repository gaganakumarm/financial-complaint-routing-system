"""Benchmark comparison repository tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import BenchmarkComparison, BenchmarkComparisonMember, BenchmarkResult
from app.repositories import BenchmarkComparisonRepository, BenchmarkResultRepository


def query_result(*values, scalar=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = list(values)
    return result


def test_constructors() -> None:
    session = MagicMock()
    assert BenchmarkComparisonRepository(session).model_type is BenchmarkComparison
    assert BenchmarkResultRepository(session).model_type is BenchmarkResult


@pytest.mark.anyio
async def test_result_batch_empty_validation_and_one_main_query() -> None:
    session = MagicMock(); session.execute = AsyncMock()
    repository = BenchmarkResultRepository(session)
    assert await repository.get_results_by_ids([]) == []
    session.execute.assert_not_awaited()
    for value in ("bad", ["bad"]):
        with pytest.raises(ValueError): await repository.get_results_by_ids(value)
    first, second = SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())
    session.execute.return_value = query_result(first, second)
    assert await repository.get_results_by_ids([second.id, first.id]) == [first, second]
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    assert len(statement._with_options) == 2
    assert len(statement._order_by_clauses) == 1


@pytest.mark.anyio
async def test_get_with_members_loads_relationships_and_orders_members() -> None:
    session = MagicMock(); session.execute = AsyncMock()
    repository = BenchmarkComparisonRepository(session); identifier = uuid4()
    comparison = SimpleNamespace(members=[SimpleNamespace(rank=2, id=uuid4()), SimpleNamespace(rank=1, id=uuid4())])
    session.execute.return_value = query_result(scalar=comparison)
    assert await repository.get_with_members(identifier) is comparison
    assert [member.rank for member in comparison.members] == [1, 2]
    statement = session.execute.await_args.args[0]
    assert len(statement._with_options) == 2
    session.execute.return_value = query_result(scalar=None)
    assert await repository.get_with_members(identifier) is None
    with pytest.raises(ValueError): await repository.get_with_members("bad")


@pytest.mark.anyio
async def test_list_is_deterministic_and_validates_pagination() -> None:
    session = MagicMock(); session.execute = AsyncMock(return_value=query_result())
    repository = BenchmarkComparisonRepository(session)
    assert await repository.list_comparisons(offset=2, limit=7) == []
    statement = session.execute.await_args.args[0]
    assert len(statement._order_by_clauses) == 2
    for offset, limit in [(-1, 1), (0, 0), (0, 501)]:
        with pytest.raises(ValueError): await repository.list_comparisons(offset=offset, limit=limit)


@pytest.mark.anyio
async def test_persistence_methods_delegate_without_transactions() -> None:
    session = MagicMock(); session.flush = AsyncMock(); session.refresh = AsyncMock()
    session.commit = AsyncMock(); session.rollback = AsyncMock(); session.begin = MagicMock()
    repository = BenchmarkComparisonRepository(session)
    comparison = BenchmarkComparison(); members = [BenchmarkComparisonMember(), BenchmarkComparisonMember()]
    assert await repository.add_comparison(comparison) is comparison
    assert await repository.add_member(members[0]) is members[0]
    assert await repository.add_members(members) is members
    await repository.flush(); assert await repository.refresh(comparison) is comparison
    session.flush.assert_awaited_once(); session.refresh.assert_awaited_once_with(comparison)
    session.commit.assert_not_awaited(); session.rollback.assert_not_awaited(); session.begin.assert_not_called()
