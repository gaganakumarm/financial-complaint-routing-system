"""Benchmark comparison service tests."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.models import BenchmarkExperimentStatus
from app.services import (
    BenchmarkComparisonInput,
    BenchmarkComparisonNotFoundError,
    BenchmarkComparisonPersistenceError,
    BenchmarkComparisonService,
    BenchmarkResultNotFoundForComparisonError,
    IncompleteBenchmarkResultError,
    IncompatibleBenchmarkDatasetError,
    InvalidBenchmarkComparisonError,
    MissingBenchmarkMetricsError,
)


def repositories():
    comparisons = MagicMock()
    comparisons.add_comparison = AsyncMock()
    comparisons.add_members = AsyncMock()
    comparisons.flush = AsyncMock()
    comparisons.get_with_members = AsyncMock(return_value=SimpleNamespace(members=[]))
    comparisons.list_comparisons = AsyncMock(return_value=[])
    comparisons.commit = AsyncMock(); comparisons.rollback = AsyncMock(); comparisons.begin = AsyncMock()
    results = MagicMock(); results.get_results_by_ids = AsyncMock()
    return comparisons, results


def dataset(*, identifier=None, content_hash="checksum", record_count=20):
    return SimpleNamespace(id=identifier or uuid4(), content_hash=content_hash, record_count=record_count)


def result(*, identifier=None, shared_dataset=None, status=BenchmarkExperimentStatus.COMPLETED, **updates):
    shared_dataset = shared_dataset or dataset()
    values = dict(
        id=identifier or uuid4(), total_error_cost=Decimal("1"),
        exact_match_accuracy=Decimal(".9"), failed_prediction_count=0,
        department_accuracy=Decimal(".9"), category_accuracy=Decimal(".9"),
        urgency_accuracy=Decimal(".9"), p95_inference_latency_ms=50,
    )
    values.update(updates)
    values["experiment"] = SimpleNamespace(
        status=status, dataset_version_id=shared_dataset.id,
        dataset_version=shared_dataset,
    )
    return SimpleNamespace(**values)


def request(results, *, creator=None, metric="  deterministic-v1  "):
    return BenchmarkComparisonInput(
        benchmark_result_ids=[value.id for value in results],
        created_by_user_id=creator or uuid4(), ranking_metric=metric,
    )


def assert_no_writes(repository) -> None:
    repository.add_comparison.assert_not_awaited()
    repository.add_members.assert_not_awaited()
    repository.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_success_derives_metadata_winner_and_order_after_validation() -> None:
    comparisons, results_repository = repositories(); shared = dataset()
    loser = result(identifier=UUID(int=2), shared_dataset=shared, total_error_cost=Decimal("2"))
    winner = result(identifier=UUID(int=1), shared_dataset=shared, total_error_cost=Decimal("1"))
    results_repository.get_results_by_ids.return_value = [loser, winner]
    complete = SimpleNamespace(members=[]); comparisons.get_with_members.return_value = complete
    service = BenchmarkComparisonService(comparisons, results_repository)
    assert await service.create_comparison(request([loser, winner])) is complete
    persisted = comparisons.add_comparison.await_args.args[0]
    assert (persisted.dataset_version_id, persisted.dataset_checksum, persisted.dataset_example_count) == (shared.id, "checksum", 20)
    assert persisted.winner_result_id == winner.id and persisted.ranking_metric == "deterministic-v1"
    members = comparisons.add_members.await_args.args[0]
    assert [(member.benchmark_result_id, member.rank) for member in members] == [(winner.id, 1), (loser.id, 2)]
    assert all(member.comparison is persisted for member in members)
    comparisons.flush.assert_awaited_once()
    comparisons.get_with_members.assert_awaited_once_with(persisted.id)
    comparisons.commit.assert_not_awaited(); comparisons.rollback.assert_not_awaited(); comparisons.begin.assert_not_awaited()


@pytest.mark.anyio
async def test_input_order_never_changes_winner_or_ranks() -> None:
    shared = dataset(); values = [result(identifier=UUID(int=n), shared_dataset=shared) for n in (3, 1, 2)]
    outputs = []
    for supplied in (values, list(reversed(values))):
        comparisons, result_repository = repositories(); result_repository.get_results_by_ids.return_value = list(reversed(supplied))
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(supplied))
        comparison = comparisons.add_comparison.await_args.args[0]
        members = comparisons.add_members.await_args.args[0]
        outputs.append((comparison.winner_result_id, [(m.benchmark_result_id, m.rank) for m in members]))
    assert outputs[0] == outputs[1]


@pytest.mark.anyio
@pytest.mark.parametrize("count", [2, 10])
async def test_boundary_candidate_counts_are_accepted(count) -> None:
    comparisons, result_repository = repositories(); shared = dataset()
    values = [result(shared_dataset=shared, total_error_cost=index) for index in range(count)]
    result_repository.get_results_by_ids.return_value = values
    await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(values))
    assert len(comparisons.add_members.await_args.args[0]) == count


@pytest.mark.anyio
@pytest.mark.parametrize("count", [1, 11])
async def test_invalid_candidate_counts_write_nothing(count) -> None:
    comparisons, result_repository = repositories(); values = [result() for _ in range(count)]
    with pytest.raises(InvalidBenchmarkComparisonError):
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(values))
    result_repository.get_results_by_ids.assert_not_awaited(); assert_no_writes(comparisons)


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["duplicate", "creator", "blank_metric", "long_metric", "collection"])
async def test_malformed_input_is_rejected_before_repository_access(change) -> None:
    comparisons, result_repository = repositories(); shared = dataset(); values = [result(shared_dataset=shared), result(shared_dataset=shared)]
    data = request(values)
    if change == "duplicate": data = BenchmarkComparisonInput([values[0].id] * 2, data.created_by_user_id, data.ranking_metric)
    elif change == "creator": data = BenchmarkComparisonInput(data.benchmark_result_ids, "bad", data.ranking_metric)
    elif change == "blank_metric": data = BenchmarkComparisonInput(data.benchmark_result_ids, data.created_by_user_id, " ")
    elif change == "long_metric": data = BenchmarkComparisonInput(data.benchmark_result_ids, data.created_by_user_id, "x" * 101)
    else: data = BenchmarkComparisonInput("not-a-collection", data.created_by_user_id, data.ranking_metric)
    with pytest.raises(InvalidBenchmarkComparisonError):
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(data)
    result_repository.get_results_by_ids.assert_not_awaited(); assert_no_writes(comparisons)


@pytest.mark.anyio
async def test_every_missing_result_is_detected_before_writes() -> None:
    comparisons, result_repository = repositories(); shared = dataset(); values = [result(shared_dataset=shared), result(shared_dataset=shared)]
    result_repository.get_results_by_ids.return_value = values[:1]
    with pytest.raises(BenchmarkResultNotFoundForComparisonError):
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(values))
    assert_no_writes(comparisons)


@pytest.mark.anyio
async def test_incomplete_result_is_rejected() -> None:
    comparisons, result_repository = repositories(); shared = dataset()
    values = [result(shared_dataset=shared), result(shared_dataset=shared, status=BenchmarkExperimentStatus.RUNNING)]
    result_repository.get_results_by_ids.return_value = values
    with pytest.raises(IncompleteBenchmarkResultError):
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(values))
    assert_no_writes(comparisons)


@pytest.mark.anyio
@pytest.mark.parametrize("metric", ["total_error_cost", "exact_match_accuracy", "failed_prediction_count", "department_accuracy", "category_accuracy", "urgency_accuracy", "p95_inference_latency_ms"])
async def test_each_missing_metric_is_rejected(metric) -> None:
    comparisons, result_repository = repositories(); shared = dataset()
    values = [result(shared_dataset=shared), result(shared_dataset=shared, **{metric: None})]
    result_repository.get_results_by_ids.return_value = values
    with pytest.raises(MissingBenchmarkMetricsError):
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(values))
    assert_no_writes(comparisons)


@pytest.mark.anyio
@pytest.mark.parametrize("case", ["id", "hash", "count", "blank", "nonpositive", "missing"])
async def test_incompatible_dataset_metadata_is_rejected(case) -> None:
    comparisons, result_repository = repositories(); first = dataset(); second = dataset(identifier=first.id)
    if case == "id": second.id = uuid4()
    elif case == "hash": second.content_hash = "different"
    elif case == "count": second.record_count = 21
    elif case == "blank": second.content_hash = " "
    elif case == "nonpositive": second.record_count = 0
    values = [result(shared_dataset=first), result(shared_dataset=second)]
    if case == "missing": values[1].experiment.dataset_version = None
    result_repository.get_results_by_ids.return_value = values
    with pytest.raises(IncompatibleBenchmarkDatasetError):
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(values))
    assert_no_writes(comparisons)


@pytest.mark.anyio
async def test_invalid_metric_value_from_ranking_writes_nothing() -> None:
    comparisons, result_repository = repositories(); shared = dataset()
    values = [result(shared_dataset=shared), result(shared_dataset=shared, total_error_cost=float("nan"))]
    result_repository.get_results_by_ids.return_value = values
    with pytest.raises(MissingBenchmarkMetricsError):
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(values))
    assert_no_writes(comparisons)


@pytest.mark.anyio
async def test_persistence_errors_are_generic_and_cancellation_propagates() -> None:
    shared = dataset(); values = [result(shared_dataset=shared), result(shared_dataset=shared)]
    comparisons, result_repository = repositories(); result_repository.get_results_by_ids.return_value = values
    comparisons.flush.side_effect = RuntimeError("secret SQL constraint")
    with pytest.raises(BenchmarkComparisonPersistenceError) as caught:
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(values))
    assert "secret" not in str(caught.value)
    comparisons, result_repository = repositories(); result_repository.get_results_by_ids.return_value = values
    comparisons.flush.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await BenchmarkComparisonService(comparisons, result_repository).create_comparison(request(values))


@pytest.mark.anyio
async def test_reads_delegate_without_writes() -> None:
    comparisons, result_repository = repositories(); service = BenchmarkComparisonService(comparisons, result_repository); identifier = uuid4(); existing = object()
    comparisons.get_with_members.return_value = existing
    assert await service.get_comparison(identifier) is existing
    assert await service.list_comparisons(offset=4, limit=8) == []
    comparisons.list_comparisons.assert_awaited_once_with(offset=4, limit=8)
    comparisons.get_with_members.return_value = None
    with pytest.raises(BenchmarkComparisonNotFoundError): await service.get_comparison(identifier)
    with pytest.raises(InvalidBenchmarkComparisonError): await service.get_comparison("bad")
    assert_no_writes(comparisons)
