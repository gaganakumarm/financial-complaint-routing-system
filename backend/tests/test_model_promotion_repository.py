"""Model promotion repository tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import ModelPromotionDecision, ModelPromotionStatus
from app.repositories import ModelPromotionRepository


def result(*values, scalar=None):
    value = MagicMock(); value.scalar_one_or_none.return_value = scalar
    value.scalars.return_value.all.return_value = list(values)
    return value


def test_constructor() -> None:
    session = MagicMock(); repository = ModelPromotionRepository(session)
    assert repository.session is session and repository.model_type is ModelPromotionDecision


@pytest.mark.anyio
async def test_get_by_id_validates_and_missing_returns_none() -> None:
    session = MagicMock(); session.get = AsyncMock(return_value=None)
    repository = ModelPromotionRepository(session); identifier = uuid4()
    assert await repository.get_by_id(identifier) is None
    session.get.assert_awaited_once_with(ModelPromotionDecision, identifier)
    with pytest.raises(ValueError): await repository.get_by_id("bad")


@pytest.mark.anyio
async def test_get_with_details_has_complete_graph_and_orders_members() -> None:
    promotion = SimpleNamespace(benchmark_comparison=SimpleNamespace(members=[SimpleNamespace(rank=2, id=uuid4()), SimpleNamespace(rank=1, id=uuid4())]))
    session = MagicMock(); session.execute = AsyncMock(return_value=result(scalar=promotion))
    repository = ModelPromotionRepository(session)
    assert await repository.get_with_details(uuid4()) is promotion
    assert [member.rank for member in promotion.benchmark_comparison.members] == [1, 2]
    statement = session.execute.await_args.args[0]
    assert len(statement._with_options) == 7
    session.execute.return_value = result(scalar=None)
    assert await repository.get_with_details(uuid4()) is None


@pytest.mark.anyio
async def test_list_filters_orders_paginates_and_eager_loads_compact_graph() -> None:
    promotion = ModelPromotionDecision(); session = MagicMock()
    session.execute = AsyncMock(return_value=result(promotion))
    repository = ModelPromotionRepository(session)
    assert await repository.list_promotions(status=ModelPromotionStatus.PENDING, offset=2, limit=7) == [promotion]
    statement = session.execute.await_args.args[0]
    assert len(statement._with_options) == 5 and len(statement._order_by_clauses) == 2
    assert "model_promotion_decisions.status" in str(statement)
    params = statement.compile().params
    assert 2 in params.values() and 7 in params.values()
    for status in ("pending", True):
        with pytest.raises(ValueError): await repository.list_promotions(status=status)
    for offset, limit in ((-1, 1), (0, 0), (0, 501)):
        with pytest.raises(ValueError): await repository.list_promotions(offset=offset, limit=limit)


@pytest.mark.anyio
async def test_pending_lookup_validates_and_is_exact() -> None:
    identifier = uuid4(); session = MagicMock(); session.execute = AsyncMock(return_value=result(scalar=None))
    repository = ModelPromotionRepository(session)
    assert await repository.get_pending_for_comparison(identifier) is None
    statement = session.execute.await_args.args[0]
    assert statement.compile().params["benchmark_comparison_id_1"] == identifier
    assert ModelPromotionStatus.PENDING in statement.compile().params.values()
    with pytest.raises(ValueError): await repository.get_pending_for_comparison(b"bad")


@pytest.mark.anyio
async def test_writes_delegate_without_transaction_ownership() -> None:
    session = MagicMock(); session.flush = AsyncMock(); session.refresh = AsyncMock()
    session.commit = AsyncMock(); session.rollback = AsyncMock(); session.begin = MagicMock()
    repository = ModelPromotionRepository(session); promotion = ModelPromotionDecision()
    assert await repository.add_promotion(promotion) is promotion
    await repository.flush(); assert await repository.refresh(promotion) is promotion
    session.add.assert_called_once_with(promotion); session.flush.assert_awaited_once(); session.refresh.assert_awaited_once_with(promotion)
    session.commit.assert_not_awaited(); session.rollback.assert_not_awaited(); session.begin.assert_not_called()
