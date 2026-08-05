"""Pure benchmark metric tests."""

from dataclasses import FrozenInstanceError
from math import inf, nan
from uuid import uuid4

import pytest

from app.benchmark import (
    BenchmarkExample, BenchmarkMetrics, BenchmarkPrediction, BenchmarkPredictor,
    calculate_benchmark_metrics, validate_examples, validate_predictions,
)
from app.benchmark.types import InvalidBenchmarkExampleError, InvalidBenchmarkPredictionError
from app.models import ComplaintUrgency


def example(identifier="one", category=None, department=None, urgency=ComplaintUrgency.MEDIUM):
    return BenchmarkExample(identifier, "title", "description", category or uuid4(), department or uuid4(), urgency)


def prediction(item, *, category=None, department=None, urgency=None, confidence=.8, latency=10):
    return BenchmarkPrediction(item.example_id, category or item.expected_category_id, department or item.expected_department_id, urgency or item.expected_urgency, confidence, latency)


def test_dtos_are_frozen_slotted_and_protocol_runtime_checkable() -> None:
    item = example()
    with pytest.raises(FrozenInstanceError): item.title = "changed"
    assert not hasattr(item, "__dict__")
    assert BenchmarkMetrics.__dataclass_params__.frozen
    assert isinstance(type("P", (), {"predict_example": lambda self, **kwargs: None})(), BenchmarkPredictor)


def test_example_and_prediction_set_validation() -> None:
    one = example()
    assert validate_examples([one]) == (one,)
    with pytest.raises(InvalidBenchmarkExampleError): validate_examples([])
    with pytest.raises(InvalidBenchmarkExampleError): validate_examples([one, one])
    valid = prediction(one)
    assert validate_predictions([valid], expected_example_ids={"one"}) == (valid,)
    for values, ids in [([], {"one"}), ([valid], {"two"}), ([valid, valid], {"one"})]:
        with pytest.raises(InvalidBenchmarkPredictionError): validate_predictions(values, expected_example_ids=ids)


@pytest.mark.parametrize(
    "item",
    [
        object(),
        BenchmarkExample(" ", "title", "description", uuid4(), uuid4(), ComplaintUrgency.MEDIUM),
        BenchmarkExample("one", "title", "description", "bad", uuid4(), ComplaintUrgency.MEDIUM),
        BenchmarkExample("one", "title", "description", uuid4(), "bad", ComplaintUrgency.MEDIUM),
        BenchmarkExample("one", "title", "description", uuid4(), uuid4(), "medium"),
    ],
)
def test_invalid_example_fields_are_rejected(item) -> None:
    with pytest.raises(InvalidBenchmarkExampleError): validate_examples([item])


@pytest.mark.parametrize("field", ["example_id", "predicted_category_id", "predicted_department_id", "predicted_urgency"])
def test_invalid_prediction_fields_are_rejected(field) -> None:
    item = example()
    values = {
        "example_id": item.example_id,
        "predicted_category_id": item.expected_category_id,
        "predicted_department_id": item.expected_department_id,
        "predicted_urgency": item.expected_urgency,
        "confidence_score": .5,
        "latency_ms": 1,
    }
    values[field] = " " if field == "example_id" else "invalid"
    output = BenchmarkPrediction(**values)
    with pytest.raises(InvalidBenchmarkPredictionError):
        validate_predictions([output], expected_example_ids={item.example_id})


@pytest.mark.parametrize("confidence", [True, nan, inf, -0.1, 1.1])
def test_invalid_confidence_rejected(confidence) -> None:
    item = example()
    with pytest.raises(InvalidBenchmarkPredictionError):
        validate_predictions([prediction(item, confidence=confidence)], expected_example_ids={item.example_id})


@pytest.mark.parametrize("latency", [True, -1, 1.5])
def test_invalid_latency_rejected(latency) -> None:
    item = example()
    with pytest.raises(InvalidBenchmarkPredictionError):
        validate_predictions([prediction(item, latency=latency)], expected_example_ids={item.example_id})


def test_perfect_and_weighted_metrics_without_mutation() -> None:
    items = [example("a"), example("b")]
    outputs = [prediction(items[0], confidence=.6, latency=1), prediction(items[1], confidence=1, latency=20)]
    before = (list(items), list(outputs))
    metrics = calculate_benchmark_metrics(examples=items, predictions=outputs)
    assert metrics.category_accuracy == metrics.department_accuracy == metrics.urgency_accuracy == 1
    assert metrics.exact_match_accuracy == metrics.macro_f1 == 1
    assert metrics.weighted_error_cost == 0
    assert metrics.average_confidence == .8
    assert metrics.average_latency_ms == 10.5
    assert metrics.p95_latency_ms == 20
    assert (items, outputs) == before


def test_partial_macro_f1_exact_match_and_custom_cost() -> None:
    category_a, category_b, category_c = uuid4(), uuid4(), uuid4()
    department = uuid4()
    items = [example("a", category_a, department), example("b", category_b, department)]
    outputs = [prediction(items[0]), prediction(items[1], category=category_c, department=uuid4(), urgency=ComplaintUrgency.HIGH)]
    metrics = calculate_benchmark_metrics(examples=items, predictions=outputs)
    assert metrics.category_accuracy == metrics.exact_match_accuracy == .5
    assert metrics.macro_f1 == pytest.approx(1 / 3)
    assert metrics.weighted_error_cost == 6.5
    custom = calculate_benchmark_metrics(examples=items, predictions=outputs, category_error_weight=3, department_error_weight=4, urgency_error_weight=5)
    assert custom.weighted_error_cost == 6


def test_completely_wrong_predictions_have_zero_scores_and_order_is_by_id() -> None:
    items = [example("a"), example("b")]
    outputs = [
        prediction(items[1], category=uuid4(), department=uuid4(), urgency=ComplaintUrgency.HIGH, confidence=.2),
        prediction(items[0], category=uuid4(), department=uuid4(), urgency=ComplaintUrgency.HIGH, confidence=.8),
    ]
    metrics = calculate_benchmark_metrics(examples=items, predictions=outputs)
    assert metrics.category_accuracy == metrics.department_accuracy == 0
    assert metrics.urgency_accuracy == metrics.exact_match_accuracy == metrics.macro_f1 == 0
    assert metrics.weighted_error_cost == 13
    assert metrics.average_confidence == .5


@pytest.mark.parametrize("weight", [True, -1, nan, inf])
def test_invalid_custom_weights_are_rejected(weight) -> None:
    item = example()
    with pytest.raises(ValueError):
        calculate_benchmark_metrics(
            examples=[item], predictions=[prediction(item)], category_error_weight=weight
        )


@pytest.mark.parametrize(("latencies", "expected"), [([7], 7), ([1, 2, 3], 3), (list(range(1, 101)), 95)])
def test_p95_uses_nearest_rank(latencies, expected) -> None:
    items = [example(str(index)) for index in range(len(latencies))]
    outputs = [prediction(item, latency=value) for item, value in zip(items, latencies)]
    assert calculate_benchmark_metrics(examples=items, predictions=outputs).p95_latency_ms == expected


def test_p95_nearest_rank_boundary_selects_nineteenth_of_twenty() -> None:
    items = [example(str(index)) for index in range(20)]
    outputs = [prediction(item, latency=index + 1) for index, item in enumerate(items)]
    assert calculate_benchmark_metrics(examples=items, predictions=outputs).p95_latency_ms == 19
