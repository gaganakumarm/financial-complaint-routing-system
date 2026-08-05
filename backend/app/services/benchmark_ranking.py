"""Pure deterministic ranking for completed benchmark results."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from numbers import Integral, Real
from collections.abc import Sequence
from uuid import UUID


class BenchmarkRankingError(ValueError):
    """Raised when benchmark ranking input is invalid."""


_INVALID = "Benchmark ranking input is invalid."


@dataclass(frozen=True, slots=True)
class BenchmarkRankingInput:
    benchmark_result_id: UUID
    total_error_cost: Decimal | float | int
    exact_match_accuracy: Decimal | float | int
    failed_prediction_count: int
    department_accuracy: Decimal | float | int
    category_accuracy: Decimal | float | int
    urgency_accuracy: Decimal | float | int
    p95_inference_latency_ms: int


@dataclass(frozen=True, slots=True)
class RankedBenchmarkResult:
    benchmark_result_id: UUID
    rank: int
    total_error_cost: Decimal
    exact_match_accuracy: Decimal
    failed_prediction_count: int
    department_accuracy: Decimal
    category_accuracy: Decimal
    urgency_accuracy: Decimal
    p95_inference_latency_ms: int


def _decimal(value: object, *, accuracy: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, Real)):
        raise BenchmarkRankingError(_INVALID)
    if isinstance(value, float) and not isfinite(value):
        raise BenchmarkRankingError(_INVALID)
    try:
        normalized = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BenchmarkRankingError(_INVALID) from None
    if not normalized.is_finite() or normalized < 0 or (accuracy and normalized > 1):
        raise BenchmarkRankingError(_INVALID)
    return normalized


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise BenchmarkRankingError(_INVALID)
    return int(value)


def rank_benchmark_results(
    results: Sequence[BenchmarkRankingInput],
) -> list[RankedBenchmarkResult]:
    """Validate and rank two to ten results without mutating the inputs."""
    if isinstance(results, (str, bytes)) or not isinstance(results, Sequence):
        raise BenchmarkRankingError(_INVALID)
    if not 2 <= len(results) <= 10:
        raise BenchmarkRankingError(_INVALID)

    normalized: list[RankedBenchmarkResult] = []
    identifiers: set[UUID] = set()
    for item in results:
        if not isinstance(item, BenchmarkRankingInput):
            raise BenchmarkRankingError(_INVALID)
        if not isinstance(item.benchmark_result_id, UUID) or item.benchmark_result_id in identifiers:
            raise BenchmarkRankingError(_INVALID)
        identifiers.add(item.benchmark_result_id)
        normalized.append(
            RankedBenchmarkResult(
                benchmark_result_id=item.benchmark_result_id,
                rank=0,
                total_error_cost=_decimal(item.total_error_cost),
                exact_match_accuracy=_decimal(item.exact_match_accuracy, accuracy=True),
                failed_prediction_count=_integer(item.failed_prediction_count),
                department_accuracy=_decimal(item.department_accuracy, accuracy=True),
                category_accuracy=_decimal(item.category_accuracy, accuracy=True),
                urgency_accuracy=_decimal(item.urgency_accuracy, accuracy=True),
                p95_inference_latency_ms=_integer(item.p95_inference_latency_ms),
            )
        )

    ordered = sorted(
        normalized,
        key=lambda item: (
            item.total_error_cost,
            -item.exact_match_accuracy,
            item.failed_prediction_count,
            -item.department_accuracy,
            -item.category_accuracy,
            -item.urgency_accuracy,
            item.p95_inference_latency_ms,
            str(item.benchmark_result_id),
        ),
    )
    return [
        RankedBenchmarkResult(
            benchmark_result_id=item.benchmark_result_id,
            rank=rank,
            total_error_cost=item.total_error_cost,
            exact_match_accuracy=item.exact_match_accuracy,
            failed_prediction_count=item.failed_prediction_count,
            department_accuracy=item.department_accuracy,
            category_accuracy=item.category_accuracy,
            urgency_accuracy=item.urgency_accuracy,
            p95_inference_latency_ms=item.p95_inference_latency_ms,
        )
        for rank, item in enumerate(ordered, start=1)
    ]


__all__ = [
    "BenchmarkRankingError",
    "BenchmarkRankingInput",
    "RankedBenchmarkResult",
    "rank_benchmark_results",
]
