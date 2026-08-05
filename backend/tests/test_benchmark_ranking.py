"""Pure benchmark-result ranking tests."""

from dataclasses import replace
from decimal import Decimal
from random import Random
from uuid import UUID, uuid4

import pytest

from app.services.benchmark_ranking import (
    BenchmarkRankingError,
    BenchmarkRankingInput,
    rank_benchmark_results,
)


def item(identifier: UUID | None = None, **updates) -> BenchmarkRankingInput:
    values = dict(
        benchmark_result_id=identifier or uuid4(),
        total_error_cost=Decimal("1.25"),
        exact_match_accuracy=Decimal("0.80"),
        failed_prediction_count=1,
        department_accuracy=Decimal("0.85"),
        category_accuracy=Decimal("0.90"),
        urgency_accuracy=Decimal("0.95"),
        p95_inference_latency_ms=100,
    )
    values.update(updates)
    return BenchmarkRankingInput(**values)


@pytest.mark.parametrize(
    "field,winner,loser",
    [
        ("total_error_cost", Decimal("1"), Decimal("2")),
        ("exact_match_accuracy", Decimal(".9"), Decimal(".8")),
        ("failed_prediction_count", 0, 1),
        ("department_accuracy", Decimal(".9"), Decimal(".8")),
        ("category_accuracy", Decimal(".9"), Decimal(".8")),
        ("urgency_accuracy", Decimal(".9"), Decimal(".8")),
        ("p95_inference_latency_ms", 50, 100),
    ],
)
def test_each_ranking_key_breaks_the_preceding_tie(field, winner, loser) -> None:
    first = item(UUID(int=2), **{field: winner})
    second = item(UUID(int=1), **{field: loser})
    assert rank_benchmark_results([second, first])[0].benchmark_result_id == first.benchmark_result_id


def test_uuid_is_final_tie_breaker_and_order_is_input_independent() -> None:
    values = [item(UUID(int=value)) for value in (3, 1, 2)]
    expected = [UUID(int=value) for value in (1, 2, 3)]
    assert [row.benchmark_result_id for row in rank_benchmark_results(values)] == expected
    assert [row.benchmark_result_id for row in rank_benchmark_results(list(reversed(values)))] == expected
    shuffled = values.copy(); Random(7).shuffle(shuffled)
    ranked = rank_benchmark_results(shuffled)
    assert [row.benchmark_result_id for row in ranked] == expected
    assert [row.rank for row in ranked] == [1, 2, 3]


@pytest.mark.parametrize("count", [0, 1, 11])
def test_size_limits(count) -> None:
    with pytest.raises(BenchmarkRankingError, match="invalid"):
        rank_benchmark_results([item() for _ in range(count)])


def test_duplicate_ids_are_rejected() -> None:
    identifier = uuid4()
    with pytest.raises(BenchmarkRankingError):
        rank_benchmark_results([item(identifier), item(identifier)])


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_error_cost", None), ("total_error_cost", -1),
        ("failed_prediction_count", -1), ("p95_inference_latency_ms", -1),
        ("exact_match_accuracy", -0.1), ("category_accuracy", 1.1),
        ("urgency_accuracy", float("nan")),
        ("department_accuracy", float("inf")),
        ("total_error_cost", float("-inf")),
        ("total_error_cost", True), ("failed_prediction_count", True),
        ("p95_inference_latency_ms", 1.5), ("total_error_cost", "1.0"),
    ],
)
def test_invalid_numeric_values_are_rejected(field, value) -> None:
    with pytest.raises(BenchmarkRankingError, match="invalid"):
        rank_benchmark_results([item(**{field: value}), item()])


def test_supported_numbers_normalize_without_mutating_inputs() -> None:
    first = item(total_error_cost=1, exact_match_accuracy=0.5)
    second = replace(first, benchmark_result_id=uuid4(), total_error_cost=Decimal("2"))
    before = (first, second)
    ranked = rank_benchmark_results(before)
    assert before == (first, second)
    assert ranked[0].total_error_cost == Decimal("1")
    assert ranked[0].exact_match_accuracy == Decimal("0.5")
