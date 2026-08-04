"""Unit tests for asynchronous repositories without a database connection."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BenchmarkExperimentStatus,
    Complaint,
    ComplaintStatus,
    DatasetSplit,
    User,
)
from app.repositories import (
    BaseRepository,
    BenchmarkExperimentRepository,
    BenchmarkResultRepository,
    ComplaintRepository,
    DatasetVersionRepository,
    ModelVersionRepository,
    PredictionRepository,
    ReviewRepository,
    UserRepository,
)


def make_session(*, rows=(), scalar=None, scalar_one=None):
    session = MagicMock(spec=AsyncSession)
    session.get = AsyncMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(rows)
    result.scalar_one_or_none.return_value = scalar
    result.scalar_one.return_value = scalar_one
    session.execute.return_value = result
    return session, result


@pytest.mark.anyio
async def test_base_repository_operations_and_transaction_neutrality() -> None:
    session, result = make_session(rows=["one", "two"])
    repository = BaseRepository(session, User)
    entity = MagicMock(spec=User)
    entity_id = uuid4()
    session.get.return_value = entity

    assert repository.session is session
    assert repository.model_type is User
    assert await repository.get_by_id(entity_id) is entity
    session.get.assert_awaited_once_with(User, entity_id)
    assert await repository.add(entity) is entity
    session.add.assert_called_once_with(entity)
    await repository.delete(entity)
    session.delete.assert_awaited_once_with(entity)
    await repository.flush()
    session.flush.assert_awaited_once()
    assert await repository.refresh(entity) is entity
    session.refresh.assert_awaited_once_with(entity)
    assert await repository.list(offset=4, limit=12) == ["one", "two"]
    statement = session.execute.await_args.args[0]
    assert statement._offset_clause.value == 4
    assert statement._limit_clause.value == 12
    result.scalars.assert_called_once()
    assert not session.commit.called
    assert not session.rollback.called
    assert not session.begin.called


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("offset", "limit"), [(-1, 100), (0, 0), (0, -1), (0, 501)]
)
async def test_base_repository_rejects_invalid_pagination(offset: int, limit: int) -> None:
    session, _ = make_session()
    with pytest.raises(ValueError):
        await BaseRepository(session, User).list(offset=offset, limit=limit)
    session.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_user_repository_email_queries_are_trimmed_and_case_insensitive() -> None:
    session, result = make_session(scalar="user", scalar_one=True)
    repository = UserRepository(session)
    assert await repository.get_by_email("  Person@Example.com  ") == "user"
    lookup = session.execute.await_args_list[0].args[0]
    compiled = lookup.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "lower(users.email) = lower(" in sql
    assert "Person@Example.com" in compiled.params.values()
    result.scalar_one_or_none.assert_called_once()

    assert await repository.email_exists(" Person@Example.com ") is True
    existence = session.execute.await_args_list[1].args[0]
    assert "EXISTS" in str(existence.compile(dialect=postgresql.dialect()))
    result.scalar_one.assert_called_once()

    for method in (repository.get_by_email, repository.email_exists):
        with pytest.raises(ValueError):
            await method("   ")


@pytest.mark.anyio
async def test_complaint_repository_queries() -> None:
    session, result = make_session(rows=["complaint"], scalar="complaint")
    repository = ComplaintRepository(session)
    assert await repository.get_by_reference_number(" REF-1 ") == "complaint"
    lookup = session.execute.await_args_list[-1].args[0]
    assert "REF-1" in lookup.compile(dialect=postgresql.dialect()).params.values()
    result.scalar_one_or_none.assert_called_once()
    with pytest.raises(ValueError):
        await repository.get_by_reference_number(" ")

    customer_id = uuid4()
    assert await repository.list_for_customer(customer_id, offset=2, limit=5) == [
        "complaint"
    ]
    customer_statement = session.execute.await_args_list[-1].args[0]
    _assert_page(customer_statement, 2, 5)
    _assert_order(customer_statement, "complaints.created_at DESC", "complaints.id DESC")

    await repository.list_review_queue()
    queue = session.execute.await_args_list[-1].args[0]
    params = queue.compile(dialect=postgresql.dialect()).params
    values = next(value for value in params.values() if isinstance(value, (list, tuple)))
    assert tuple(values) == (
        ComplaintStatus.AWAITING_REVIEW,
        ComplaintStatus.UNDER_REVIEW,
    )
    _assert_order(queue, "complaints.created_at ASC", "complaints.id ASC")
    with pytest.raises(ValueError):
        await repository.list_review_queue(statuses=[])


@pytest.mark.anyio
async def test_model_version_repository_queries() -> None:
    session, result = make_session(rows=["model"], scalar="model")
    repository = ModelVersionRepository(session)
    assert await repository.get_by_name_and_version(" router ", " 1.0 ") == "model"
    params = session.execute.await_args.args[0].compile(
        dialect=postgresql.dialect()
    ).params.values()
    assert "router" in params and "1.0" in params
    for name, version in (("", "1"), ("name", " ")):
        with pytest.raises(ValueError):
            await repository.get_by_name_and_version(name, version)
    await repository.get_active()
    assert "model_versions.is_active IS true" in str(
        session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    )
    await repository.list_approved(offset=3, limit=7)
    statement = session.execute.await_args.args[0]
    assert "model_versions.is_approved IS true" in str(
        statement.compile(dialect=postgresql.dialect())
    )
    _assert_page(statement, 3, 7)
    _assert_order(statement, "model_versions.created_at DESC", "model_versions.id DESC")


@pytest.mark.anyio
async def test_prediction_repository_queries() -> None:
    session, result = make_session(rows=["prediction"], scalar="prediction")
    repository = PredictionRepository(session)
    complaint_id = uuid4()
    assert await repository.list_for_complaint(complaint_id, offset=1, limit=9) == [
        "prediction"
    ]
    statement = session.execute.await_args.args[0]
    _assert_page(statement, 1, 9)
    _assert_order(statement, "predictions.created_at DESC", "predictions.id DESC")
    assert await repository.get_latest_for_complaint(complaint_id) == "prediction"
    latest = session.execute.await_args.args[0]
    assert latest._limit_clause.value == 1
    _assert_order(latest, "predictions.created_at DESC", "predictions.id DESC")
    result.scalar_one_or_none.assert_called_once()


@pytest.mark.anyio
async def test_review_repository_queries() -> None:
    session, result = make_session(rows=["review"], scalar="review")
    repository = ReviewRepository(session)
    assert await repository.get_for_prediction(uuid4()) == "review"
    result.scalar_one_or_none.assert_called_once()
    await repository.list_for_reviewer(uuid4(), offset=2, limit=8)
    reviewer_statement = session.execute.await_args.args[0]
    _assert_page(reviewer_statement, 2, 8)
    _assert_order(reviewer_statement, "reviews.created_at DESC", "reviews.id DESC")
    await repository.list_pending()
    pending_statement = session.execute.await_args.args[0]
    assert "reviews.outcome" in str(pending_statement.compile(dialect=postgresql.dialect()))
    _assert_order(pending_statement, "reviews.created_at ASC", "reviews.id ASC")


@pytest.mark.anyio
async def test_dataset_version_repository_queries() -> None:
    session, result = make_session(scalar="dataset")
    repository = DatasetVersionRepository(session)
    assert await repository.get_by_identity(
        name=" data ", version=" v1 ", split=DatasetSplit.TEST
    ) == "dataset"
    params = session.execute.await_args.args[0].compile(
        dialect=postgresql.dialect()
    ).params.values()
    assert "data" in params and "v1" in params and DatasetSplit.TEST in params
    assert await repository.get_by_content_hash(" abc ") == "dataset"
    assert "abc" in session.execute.await_args.args[0].compile(
        dialect=postgresql.dialect()
    ).params.values()
    for method in (
        lambda: repository.get_by_identity(name=" ", version="v", split=DatasetSplit.TEST),
        lambda: repository.get_by_content_hash(" "),
    ):
        with pytest.raises(ValueError):
            await method()
    assert result.scalar_one_or_none.call_count == 2


@pytest.mark.anyio
async def test_benchmark_experiment_repository_queries() -> None:
    session, _ = make_session(rows=["experiment"])
    repository = BenchmarkExperimentRepository(session)
    assert await repository.list_by_status(
        BenchmarkExperimentStatus.COMPLETED, offset=1, limit=4
    ) == ["experiment"]
    status_statement = session.execute.await_args.args[0]
    _assert_page(status_statement, 1, 4)
    _assert_order(
        status_statement,
        "benchmark_experiments.created_at DESC",
        "benchmark_experiments.id DESC",
    )
    await repository.list_for_dataset(uuid4(), offset=2, limit=6)
    _assert_page(session.execute.await_args.args[0], 2, 6)


@pytest.mark.anyio
async def test_benchmark_result_repository_queries() -> None:
    session, result = make_session(rows=["result"], scalar="result")
    repository = BenchmarkResultRepository(session)
    assert await repository.get_for_experiment_and_model(
        experiment_id=uuid4(), model_version_id=uuid4()
    ) == "result"
    result.scalar_one_or_none.assert_called_once()
    assert await repository.list_for_experiment(uuid4()) == ["result"]
    statement = session.execute.await_args.args[0]
    _assert_order(
        statement,
        "benchmark_results.created_at ASC",
        "benchmark_results.id ASC",
    )


def _assert_page(statement, offset: int, limit: int) -> None:
    assert statement._offset_clause.value == offset
    assert statement._limit_clause.value == limit


def _assert_order(statement, *expected: str) -> None:
    actual = tuple(str(item) for item in statement._order_by_clauses)
    assert actual == expected
