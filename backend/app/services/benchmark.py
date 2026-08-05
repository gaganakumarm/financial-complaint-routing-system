"""Transaction-neutral benchmark experiment orchestration."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.benchmark.metrics import aggregate_benchmark_outcomes, calculate_benchmark_outcome, validate_examples
from app.benchmark.types import (
    BenchmarkError,
    BenchmarkExample,
    BenchmarkExecutionError,
    BenchmarkExperimentNotFoundError,
    BenchmarkPersistenceError,
    BenchmarkPredictorFactory,
    BenchmarkResultNotFoundError,
    DatasetVersionNotFoundError,
    DuplicateBenchmarkResultError,
    InvalidBenchmarkExampleError,
    InvalidBenchmarkPredictionError,
    ModelVersionNotFoundError,
)
from app.models import (
    BenchmarkExampleResult, BenchmarkExperiment, BenchmarkExperimentStatus, BenchmarkResult, ModelVersion,
)
from app.repositories import (
    BenchmarkExperimentRepository, BenchmarkResultRepository,
    BenchmarkExampleResultRepository, DatasetExampleRepository, DatasetVersionRepository, ModelVersionRepository,
)


_EXECUTION_FAILED = "Benchmark execution failed."
_PERSISTENCE_FAILED = "Benchmark result persistence failed."


class BenchmarkService:
    def __init__(
        self, *, dataset_version_repository: DatasetVersionRepository,
        benchmark_experiment_repository: BenchmarkExperimentRepository,
        benchmark_result_repository: BenchmarkResultRepository,
        model_version_repository: ModelVersionRepository,
        predictor_factory: BenchmarkPredictorFactory,
        dataset_example_repository: DatasetExampleRepository | None = None,
        benchmark_example_result_repository: BenchmarkExampleResultRepository | None = None,
    ) -> None:
        self._dataset_version_repository = dataset_version_repository
        self._benchmark_experiment_repository = benchmark_experiment_repository
        self._benchmark_result_repository = benchmark_result_repository
        self._model_version_repository = model_version_repository
        self._predictor_factory = predictor_factory
        self._dataset_example_repository = dataset_example_repository
        self._benchmark_example_result_repository = benchmark_example_result_repository

    @staticmethod
    def _fail(experiment: BenchmarkExperiment) -> None:
        experiment.status = BenchmarkExperimentStatus.FAILED
        experiment.completed_at = datetime.now(timezone.utc)
        experiment.failure_message = _EXECUTION_FAILED

    @staticmethod
    def _cancel(experiment: BenchmarkExperiment) -> None:
        experiment.status = BenchmarkExperimentStatus.CANCELLED
        experiment.completed_at = datetime.now(timezone.utc)
        experiment.failure_message = None

    async def run_experiment(self, *, experiment: BenchmarkExperiment, model_versions, examples=None) -> list[BenchmarkResult]:
        if not isinstance(experiment, BenchmarkExperiment):
            raise BenchmarkExecutionError("Benchmark experiment is invalid.")
        experiment_id = experiment.__dict__.get("id")
        dataset_version_id = experiment.__dict__.get("dataset_version_id")
        if not isinstance(experiment_id, UUID) or not isinstance(dataset_version_id, UUID):
            raise BenchmarkExecutionError("Benchmark experiment is invalid.")
        if experiment.status is not BenchmarkExperimentStatus.PENDING:
            raise BenchmarkExecutionError("Benchmark experiment cannot be started.")
        dataset_rows = None
        if self._dataset_example_repository is not None:
            dataset_rows = await self._dataset_example_repository.list_all_for_dataset(dataset_version_id)
            examples = [BenchmarkExample(row.example_id, row.title, row.description, row.expected_category_id, row.expected_department_id, row.expected_urgency) for row in dataset_rows]
        checked_examples = validate_examples(examples)
        try:
            versions = tuple(model_versions)
        except TypeError:
            raise ModelVersionNotFoundError("Model versions are invalid.") from None
        if not versions:
            raise ModelVersionNotFoundError("Model versions were not found.")
        if any(not isinstance(version, ModelVersion) for version in versions):
            raise ModelVersionNotFoundError("Model versions are invalid.")
        ids = [version.__dict__.get("id") for version in versions]
        if any(not isinstance(value, UUID) for value in ids) or len(set(ids)) != len(ids):
            raise ModelVersionNotFoundError("Model versions are invalid.")
        if await self._dataset_version_repository.get_by_id(dataset_version_id) is None:
            raise DatasetVersionNotFoundError("Dataset version was not found.")
        authoritative_versions: list[ModelVersion] = []
        for version_id in ids:
            persisted = await self._model_version_repository.get_by_id(version_id)
            if not isinstance(persisted, ModelVersion):
                raise ModelVersionNotFoundError("Model version was not found.")
            persisted_id = persisted.__dict__.get("id")
            if not isinstance(persisted_id, UUID) or persisted_id != version_id:
                raise ModelVersionNotFoundError("Model version is invalid.")
            if not persisted.is_approved:
                raise ModelVersionNotFoundError("Model version is not approved.")
            existing = await self._benchmark_result_repository.get_for_experiment_and_model(
                experiment_id=experiment_id, model_version_id=persisted_id
            )
            if existing is not None:
                raise DuplicateBenchmarkResultError("Benchmark result already exists.")
            authoritative_versions.append(persisted)

        experiment.status = BenchmarkExperimentStatus.RUNNING
        experiment.started_at = datetime.now(timezone.utc)
        experiment.completed_at = None
        experiment.failure_message = None
        results: list[BenchmarkResult] = []
        for version in authoritative_versions:
            version_id = version.id
            try:
                predictor = self._predictor_factory(version)
                outcomes = []
                for example in checked_examples:
                    try:
                        prediction = await predictor.predict_example(example=example, model_version=version)
                    except asyncio.CancelledError:
                        self._cancel(experiment); raise
                    except Exception:
                        outcomes.append(calculate_benchmark_outcome(example=example, prediction=None, failure_code="predictor_error"))
                    else:
                        try:
                            outcomes.append(calculate_benchmark_outcome(example=example, prediction=prediction))
                        except InvalidBenchmarkPredictionError:
                            outcomes.append(calculate_benchmark_outcome(example=example, prediction=None, failure_code="invalid_output"))
                metrics = aggregate_benchmark_outcomes(outcomes)
            except asyncio.CancelledError:
                self._cancel(experiment)
                raise
            except Exception:
                self._fail(experiment)
                raise BenchmarkExecutionError(_EXECUTION_FAILED) from None
            result = BenchmarkResult(
                benchmark_experiment_id=experiment_id,
                model_version_id=version_id,
                sample_count=metrics.sample_count,
                accuracy=Decimal(str(metrics.exact_match_accuracy)),
                macro_precision=None,
                macro_recall=None,
                macro_f1=Decimal(str(metrics.macro_f1)),
                cost_weighted_error=Decimal(str(metrics.weighted_error_cost)),
                structured_output_validity_rate=Decimal(str(metrics.structured_output_validity_rate)),
                average_inference_latency_ms=Decimal(str(metrics.average_latency_ms)),
                # No wall-clock experiment throughput is measured.
                throughput_per_second=None,
                estimated_cost=None,
                per_class_metrics=None,
                additional_metrics={
                    "correct_category_count": metrics.correct_category_count,
                    "correct_department_count": metrics.correct_department_count,
                    "correct_urgency_count": metrics.correct_urgency_count,
                    "exact_match_count": metrics.exact_match_count,
                    "category_accuracy": metrics.category_accuracy,
                    "department_accuracy": metrics.department_accuracy,
                    "urgency_accuracy": metrics.urgency_accuracy,
                    "exact_match_accuracy": metrics.exact_match_accuracy,
                    "average_confidence": metrics.average_confidence,
                    "p95_latency_ms": metrics.p95_latency_ms,
                },
                total_error_cost=Decimal(str(metrics.total_error_cost)),
                exact_match_accuracy=Decimal(str(metrics.exact_match_accuracy)),
                failed_prediction_count=metrics.failed_prediction_count,
                category_accuracy=Decimal(str(metrics.category_accuracy)),
                department_accuracy=Decimal(str(metrics.department_accuracy)),
                urgency_accuracy=Decimal(str(metrics.urgency_accuracy)),
                p95_inference_latency_ms=metrics.p95_latency_ms,
            )
            try:
                await self._benchmark_result_repository.add(result)
                if dataset_rows is not None and self._benchmark_example_result_repository is not None:
                    for row, outcome in zip(dataset_rows, outcomes, strict=True):
                        await self._benchmark_example_result_repository.add(BenchmarkExampleResult(benchmark_result=result, dataset_example_id=row.id, predicted_category_id=outcome.predicted_category_id, predicted_department_id=outcome.predicted_department_id, predicted_urgency=outcome.predicted_urgency, confidence=Decimal(str(outcome.confidence_score)) if outcome.confidence_score is not None else None, inference_latency_ms=outcome.latency_ms, prediction_succeeded=outcome.prediction_succeeded, structured_output_valid=outcome.structured_output_valid, failure_code=outcome.failure_code, category_correct=outcome.category_correct, department_correct=outcome.department_correct, urgency_correct=outcome.urgency_correct, exact_match=outcome.exact_match, error_cost=Decimal(str(outcome.error_cost))))
                await self._benchmark_result_repository.flush()
                result = await self._benchmark_result_repository.refresh(result)
            except asyncio.CancelledError:
                self._cancel(experiment)
                raise
            except Exception:
                self._fail(experiment)
                raise BenchmarkPersistenceError(_PERSISTENCE_FAILED) from None
            results.append(result)
        experiment.status = BenchmarkExperimentStatus.COMPLETED
        experiment.completed_at = datetime.now(timezone.utc)
        return results

    async def get_experiment(self, experiment_id: UUID) -> BenchmarkExperiment:
        value = await self._benchmark_experiment_repository.get_by_id(experiment_id)
        if value is None:
            raise BenchmarkExperimentNotFoundError("Benchmark experiment was not found.")
        return value

    async def get_result(self, result_id: UUID) -> BenchmarkResult:
        value = await self._benchmark_result_repository.get_by_id(result_id)
        if value is None:
            raise BenchmarkResultNotFoundError("Benchmark result was not found.")
        return value

    async def list_experiment_results(self, *, experiment_id: UUID, offset: int = 0, limit: int = 100) -> list[BenchmarkResult]:
        if offset < 0 or limit < 1 or limit > 500:
            raise ValueError("invalid pagination")
        values = await self._benchmark_result_repository.list_for_experiment(experiment_id)
        return values[offset:offset + limit]

    async def list_dataset_experiments(self, *, dataset_version_id: UUID, offset: int = 0, limit: int = 100) -> list[BenchmarkExperiment]:
        return await self._benchmark_experiment_repository.list_for_dataset(
            dataset_version_id, offset=offset, limit=limit
        )


__all__ = [
    "BenchmarkError", "BenchmarkExecutionError", "BenchmarkExperimentNotFoundError",
    "BenchmarkPersistenceError", "BenchmarkResultNotFoundError", "BenchmarkService",
    "DatasetVersionNotFoundError", "DuplicateBenchmarkResultError",
    "InvalidBenchmarkExampleError", "InvalidBenchmarkPredictionError",
    "ModelVersionNotFoundError",
]
