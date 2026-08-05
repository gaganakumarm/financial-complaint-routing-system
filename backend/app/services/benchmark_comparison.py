"""Validation and persistence orchestration for benchmark comparisons."""

from collections.abc import Collection
from dataclasses import dataclass
from uuid import UUID

from app.models import (
    BenchmarkComparison,
    BenchmarkComparisonMember,
    BenchmarkExperimentStatus,
    BenchmarkResult,
)
from app.repositories import BenchmarkResultRepository
from app.repositories.benchmark_comparison import BenchmarkComparisonRepository
from app.services.benchmark_ranking import (
    BenchmarkRankingError,
    BenchmarkRankingInput,
    rank_benchmark_results,
)


class BenchmarkComparisonServiceError(Exception):
    pass


class BenchmarkComparisonNotFoundError(BenchmarkComparisonServiceError):
    pass


class BenchmarkResultNotFoundForComparisonError(BenchmarkComparisonServiceError):
    pass


class InvalidBenchmarkComparisonError(BenchmarkComparisonServiceError):
    pass


class IncompleteBenchmarkResultError(BenchmarkComparisonServiceError):
    pass


class MissingBenchmarkMetricsError(BenchmarkComparisonServiceError):
    pass


class IncompatibleBenchmarkDatasetError(BenchmarkComparisonServiceError):
    pass


class BenchmarkComparisonPersistenceError(BenchmarkComparisonServiceError):
    pass


_INVALID = "Benchmark comparison data is invalid."


@dataclass(frozen=True, slots=True)
class BenchmarkComparisonInput:
    benchmark_result_ids: Collection[UUID]
    created_by_user_id: UUID
    ranking_metric: str


class BenchmarkComparisonService:
    def __init__(
        self,
        comparison_repository: BenchmarkComparisonRepository,
        result_repository: BenchmarkResultRepository,
    ) -> None:
        self._comparisons = comparison_repository
        self._results = result_repository

    async def create_comparison(
        self, comparison_input: BenchmarkComparisonInput
    ) -> BenchmarkComparison:
        identifiers, creator_id, ranking_metric = self._validate_input(comparison_input)
        results = await self._results.get_results_by_ids(identifiers)
        by_id = {result.id: result for result in results}
        if any(identifier not in by_id for identifier in identifiers):
            raise BenchmarkResultNotFoundForComparisonError(
                "A benchmark result was not found."
            )
        ordered_results = [by_id[identifier] for identifier in identifiers]
        dataset = self._validate_compatibility(ordered_results)
        try:
            ranked = rank_benchmark_results(
                [self._ranking_input(result) for result in ordered_results]
            )
        except BenchmarkRankingError:
            raise MissingBenchmarkMetricsError(
                "Benchmark result metrics are unavailable."
            ) from None

        comparison = BenchmarkComparison(
            dataset_version_id=dataset.id,
            dataset_checksum=dataset.content_hash,
            dataset_example_count=dataset.record_count,
            winner_result_id=ranked[0].benchmark_result_id,
            ranking_metric=ranking_metric,
            created_by_user_id=creator_id,
        )
        members = [
            BenchmarkComparisonMember(
                comparison=comparison,
                benchmark_result_id=item.benchmark_result_id,
                rank=item.rank,
            )
            for item in ranked
        ]
        try:
            await self._comparisons.add_comparison(comparison)
            await self._comparisons.add_members(members)
            await self._comparisons.flush()
            complete = await self._comparisons.get_with_members(comparison.id)
        except Exception:
            raise BenchmarkComparisonPersistenceError(
                "Benchmark comparison could not be persisted."
            ) from None
        if complete is None:
            raise BenchmarkComparisonPersistenceError(
                "Benchmark comparison could not be persisted."
            )
        return complete

    async def get_comparison(self, comparison_id: UUID) -> BenchmarkComparison:
        if not isinstance(comparison_id, UUID):
            raise InvalidBenchmarkComparisonError(_INVALID)
        comparison = await self._comparisons.get_with_members(comparison_id)
        if comparison is None:
            raise BenchmarkComparisonNotFoundError(
                "Benchmark comparison was not found."
            )
        return comparison

    async def list_comparisons(
        self, *, offset: int = 0, limit: int = 100
    ) -> list[BenchmarkComparison]:
        return await self._comparisons.list_comparisons(offset=offset, limit=limit)

    @staticmethod
    def _validate_input(
        value: BenchmarkComparisonInput,
    ) -> tuple[tuple[UUID, ...], UUID, str]:
        if not isinstance(value, BenchmarkComparisonInput):
            raise InvalidBenchmarkComparisonError(_INVALID)
        identifiers_value = value.benchmark_result_ids
        if isinstance(identifiers_value, (str, bytes)) or not isinstance(
            identifiers_value, Collection
        ):
            raise InvalidBenchmarkComparisonError(_INVALID)
        identifiers = tuple(identifiers_value)
        if not 2 <= len(identifiers) <= 10:
            raise InvalidBenchmarkComparisonError(_INVALID)
        if any(not isinstance(identifier, UUID) for identifier in identifiers):
            raise InvalidBenchmarkComparisonError(_INVALID)
        if len(set(identifiers)) != len(identifiers):
            raise InvalidBenchmarkComparisonError(_INVALID)
        if not isinstance(value.created_by_user_id, UUID):
            raise InvalidBenchmarkComparisonError(_INVALID)
        if not isinstance(value.ranking_metric, str):
            raise InvalidBenchmarkComparisonError(_INVALID)
        ranking_metric = value.ranking_metric.strip()
        if not ranking_metric or len(ranking_metric) > 100:
            raise InvalidBenchmarkComparisonError(_INVALID)
        return identifiers, value.created_by_user_id, ranking_metric

    @staticmethod
    def _validate_compatibility(results: list[BenchmarkResult]):
        if any(
            result.experiment is None
            or result.experiment.status is not BenchmarkExperimentStatus.COMPLETED
            for result in results
        ):
            raise IncompleteBenchmarkResultError(
                "A benchmark result is not complete."
            )
        if any(
            metric is None
            for result in results
            for metric in (
                result.total_error_cost,
                result.exact_match_accuracy,
                result.failed_prediction_count,
                result.department_accuracy,
                result.category_accuracy,
                result.urgency_accuracy,
                result.p95_inference_latency_ms,
            )
        ):
            raise MissingBenchmarkMetricsError(
                "Benchmark result metrics are unavailable."
            )
        dataset_ids = {result.experiment.dataset_version_id for result in results}
        datasets = [result.experiment.dataset_version for result in results]
        if len(dataset_ids) != 1 or any(dataset is None for dataset in datasets):
            raise IncompatibleBenchmarkDatasetError(
                "Benchmark results use incompatible datasets."
            )
        dataset = datasets[0]
        checksums = {item.content_hash for item in datasets}
        counts = {item.record_count for item in datasets}
        if (
            len(checksums) != 1
            or len(counts) != 1
            or not isinstance(dataset.content_hash, str)
            or not dataset.content_hash.strip()
            or isinstance(dataset.record_count, bool)
            or not isinstance(dataset.record_count, int)
            or dataset.record_count <= 0
        ):
            raise IncompatibleBenchmarkDatasetError(
                "Benchmark results use incompatible datasets."
            )
        return dataset

    @staticmethod
    def _ranking_input(result: BenchmarkResult) -> BenchmarkRankingInput:
        return BenchmarkRankingInput(
            benchmark_result_id=result.id,
            total_error_cost=result.total_error_cost,
            exact_match_accuracy=result.exact_match_accuracy,
            failed_prediction_count=result.failed_prediction_count,
            department_accuracy=result.department_accuracy,
            category_accuracy=result.category_accuracy,
            urgency_accuracy=result.urgency_accuracy,
            p95_inference_latency_ms=result.p95_inference_latency_ms,
        )


__all__ = [
    "BenchmarkComparisonInput",
    "BenchmarkComparisonNotFoundError",
    "BenchmarkComparisonPersistenceError",
    "BenchmarkComparisonService",
    "BenchmarkComparisonServiceError",
    "BenchmarkResultNotFoundForComparisonError",
    "IncompleteBenchmarkResultError",
    "IncompatibleBenchmarkDatasetError",
    "InvalidBenchmarkComparisonError",
    "MissingBenchmarkMetricsError",
]
