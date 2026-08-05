"""Immutable benchmark inputs, outputs, metrics, and predictor contracts."""

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.models import Complaint, ComplaintUrgency, ModelVersion
from app.prediction import ConfiguredBaselinePredictor


class BenchmarkError(Exception):
    pass


class InvalidBenchmarkExampleError(BenchmarkError):
    pass


class InvalidBenchmarkPredictionError(BenchmarkError):
    pass


class BenchmarkExecutionError(BenchmarkError):
    pass


class BenchmarkPersistenceError(BenchmarkError):
    pass


class DatasetVersionNotFoundError(BenchmarkError):
    pass


class ModelVersionNotFoundError(BenchmarkError):
    pass


class BenchmarkExperimentNotFoundError(BenchmarkError):
    pass


class BenchmarkResultNotFoundError(BenchmarkError):
    pass


class DuplicateBenchmarkResultError(BenchmarkError):
    pass


@dataclass(frozen=True, slots=True)
class BenchmarkExample:
    example_id: str
    title: str
    description: str
    expected_category_id: UUID
    expected_department_id: UUID
    expected_urgency: ComplaintUrgency


@dataclass(frozen=True, slots=True)
class BenchmarkPrediction:
    example_id: str
    predicted_category_id: UUID
    predicted_department_id: UUID
    predicted_urgency: ComplaintUrgency
    confidence_score: float
    latency_ms: int


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    sample_count: int
    correct_category_count: int
    correct_department_count: int
    correct_urgency_count: int
    exact_match_count: int
    category_accuracy: float
    department_accuracy: float
    urgency_accuracy: float
    exact_match_accuracy: float
    macro_f1: float
    weighted_error_cost: float
    average_confidence: float
    average_latency_ms: float
    p95_latency_ms: int
    total_error_cost: float = 0.0
    failed_prediction_count: int = 0
    structured_output_validity_rate: float = 1.0


@dataclass(frozen=True, slots=True)
class BenchmarkOutcome:
    example_id: str
    predicted_category_id: UUID | None
    predicted_department_id: UUID | None
    predicted_urgency: ComplaintUrgency | None
    confidence_score: float | None
    latency_ms: int | None
    prediction_succeeded: bool
    structured_output_valid: bool
    failure_code: str | None
    category_correct: bool
    department_correct: bool
    urgency_correct: bool
    exact_match: bool
    error_cost: float


@runtime_checkable
class BenchmarkPredictor(Protocol):
    async def predict_example(
        self, *, example: BenchmarkExample, model_version: ModelVersion
    ) -> BenchmarkPrediction: ...


@runtime_checkable
class BenchmarkPredictorFactory(Protocol):
    def __call__(self, model_version: ModelVersion) -> BenchmarkPredictor: ...


class ConfiguredBenchmarkPredictor:
    """Adapt configured complaint prediction to the benchmark DTO boundary."""

    def __init__(self) -> None:
        self._predictor = ConfiguredBaselinePredictor()

    async def predict_example(
        self, *, example: BenchmarkExample, model_version: ModelVersion
    ) -> BenchmarkPrediction:
        complaint = Complaint(title=example.title, description=example.description)
        started = perf_counter()
        output = await self._predictor.predict(
            complaint=complaint, model_version=model_version
        )
        return BenchmarkPrediction(
            example_id=example.example_id,
            predicted_category_id=output.category_id,
            predicted_department_id=output.department_id,
            predicted_urgency=output.urgency,
            confidence_score=output.confidence_score,
            latency_ms=max(0, int((perf_counter() - started) * 1000)),
        )
