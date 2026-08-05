"""Pure benchmark validation and metric calculation."""

from math import ceil, isfinite
from numbers import Real
from collections.abc import Collection, Sequence
from uuid import UUID

from app.benchmark.types import (
    BenchmarkExample, BenchmarkMetrics, BenchmarkPrediction,
    InvalidBenchmarkExampleError, InvalidBenchmarkPredictionError,
)
from app.models import ComplaintUrgency


def validate_examples(examples: Sequence[BenchmarkExample]) -> tuple[BenchmarkExample, ...]:
    if isinstance(examples, (str, bytes)) or not isinstance(examples, Sequence) or not examples:
        raise InvalidBenchmarkExampleError("Benchmark examples are invalid.")
    validated = tuple(examples)
    identifiers: set[str] = set()
    for item in validated:
        if (
            not isinstance(item, BenchmarkExample)
            or not isinstance(item.example_id, str)
            or not item.example_id.strip()
            or item.example_id in identifiers
            or not isinstance(item.title, str)
            or not isinstance(item.description, str)
            or not isinstance(item.expected_category_id, UUID)
            or not isinstance(item.expected_department_id, UUID)
            or not isinstance(item.expected_urgency, ComplaintUrgency)
        ):
            raise InvalidBenchmarkExampleError("Benchmark examples are invalid.")
        identifiers.add(item.example_id)
    return validated


def validate_predictions(
    predictions: Sequence[BenchmarkPrediction], *, expected_example_ids: Collection[str]
) -> tuple[BenchmarkPrediction, ...]:
    if isinstance(predictions, (str, bytes)) or not isinstance(predictions, Sequence):
        raise InvalidBenchmarkPredictionError("Benchmark predictions are invalid.")
    expected = set(expected_example_ids)
    validated = tuple(predictions)
    identifiers: set[str] = set()
    for item in validated:
        confidence = getattr(item, "confidence_score", None)
        latency = getattr(item, "latency_ms", None)
        if (
            not isinstance(item, BenchmarkPrediction)
            or not isinstance(item.example_id, str)
            or not item.example_id.strip()
            or item.example_id in identifiers
            or not isinstance(item.predicted_category_id, UUID)
            or not isinstance(item.predicted_department_id, UUID)
            or not isinstance(item.predicted_urgency, ComplaintUrgency)
            or isinstance(confidence, bool)
            or not isinstance(confidence, Real)
            or not isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
            or isinstance(latency, bool)
            or not isinstance(latency, int)
            or latency < 0
        ):
            raise InvalidBenchmarkPredictionError("Benchmark predictions are invalid.")
        identifiers.add(item.example_id)
    if identifiers != expected or len(validated) != len(expected):
        raise InvalidBenchmarkPredictionError("Benchmark predictions are invalid.")
    return validated


def _macro_f1(examples, predictions) -> float:
    expected = {item.example_id: item.expected_category_id for item in examples}
    predicted = {item.example_id: item.predicted_category_id for item in predictions}
    labels = set(expected.values()) | set(predicted.values())
    scores = []
    for label in labels:
        true_positive = sum(expected[key] == label and predicted[key] == label for key in expected)
        false_positive = sum(expected[key] != label and predicted[key] == label for key in expected)
        false_negative = sum(expected[key] == label and predicted[key] != label for key in expected)
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores)


def calculate_benchmark_metrics(
    *, examples: Sequence[BenchmarkExample], predictions: Sequence[BenchmarkPrediction],
    category_error_weight: float = 10.0, department_error_weight: float = 2.0,
    urgency_error_weight: float = 1.0,
) -> BenchmarkMetrics:
    checked_examples = validate_examples(examples)
    checked_predictions = validate_predictions(
        predictions, expected_example_ids=[item.example_id for item in checked_examples]
    )
    weights = (category_error_weight, department_error_weight, urgency_error_weight)
    if any(isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) or value < 0 for value in weights):
        raise ValueError("Benchmark error weights are invalid.")
    by_id = {item.example_id: item for item in checked_predictions}
    category = department = urgency = exact = 0
    total_cost = 0.0
    for example in checked_examples:
        prediction = by_id[example.example_id]
        category_ok = prediction.predicted_category_id == example.expected_category_id
        department_ok = prediction.predicted_department_id == example.expected_department_id
        urgency_ok = prediction.predicted_urgency is example.expected_urgency
        category += category_ok
        department += department_ok
        urgency += urgency_ok
        exact += category_ok and department_ok and urgency_ok
        total_cost += (not category_ok) * category_error_weight + (not department_ok) * department_error_weight + (not urgency_ok) * urgency_error_weight
    count = len(checked_examples)
    latencies = sorted(item.latency_ms for item in checked_predictions)
    return BenchmarkMetrics(
        sample_count=count, correct_category_count=category,
        correct_department_count=department, correct_urgency_count=urgency,
        exact_match_count=exact, category_accuracy=category / count,
        department_accuracy=department / count, urgency_accuracy=urgency / count,
        exact_match_accuracy=exact / count,
        macro_f1=_macro_f1(checked_examples, checked_predictions),
        weighted_error_cost=total_cost / count,
        average_confidence=sum(item.confidence_score for item in checked_predictions) / count,
        average_latency_ms=sum(latencies) / count,
        # Nearest rank: sorted value at one-based rank ceil(0.95 * n).
        p95_latency_ms=latencies[ceil(0.95 * count) - 1],
    )
