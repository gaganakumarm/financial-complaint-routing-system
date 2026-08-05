"""Focused outcome model, metric, repository, and execution tests."""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from sqlalchemy import CheckConstraint
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.benchmark.metrics import aggregate_benchmark_outcomes, calculate_benchmark_outcome
from app.benchmark.types import BenchmarkExample, BenchmarkOutcome, BenchmarkPrediction, InvalidBenchmarkPredictionError
from app.models import BenchmarkExampleResult, BenchmarkExperiment, BenchmarkExperimentStatus, BenchmarkResult, ComplaintUrgency, DatasetExample, ModelVersion
from app.repositories import BenchmarkExampleResultRepository
from app.services import BenchmarkService
from app.core.config import Settings
from app.main import create_app


def example(example_id="one"):
    return BenchmarkExample(example_id, "title", "description", uuid4(), uuid4(), ComplaintUrgency.HIGH)


def prediction(item, *, category=None, department=None, urgency=None, latency=10):
    return BenchmarkPrediction(item.example_id, category or item.expected_category_id, department or item.expected_department_id, urgency or item.expected_urgency, .8, latency)


def test_outcome_model_contract() -> None:
    table = BenchmarkExampleResult.__table__
    assert set(table.c.keys()) == {"id", "benchmark_result_id", "dataset_example_id", "predicted_category_id", "predicted_department_id", "predicted_urgency", "confidence", "inference_latency_ms", "prediction_succeeded", "structured_output_valid", "failure_code", "category_correct", "department_correct", "urgency_correct", "exact_match", "error_cost", "created_at"}
    assert {constraint.name for constraint in table.constraints if isinstance(constraint, CheckConstraint)} == {"ck_benchmark_example_results_latency_non_negative", "ck_benchmark_example_results_confidence_range", "ck_benchmark_example_results_error_cost_non_negative", "ck_benchmark_example_results_failure_code_not_blank", "ck_benchmark_example_results_success_values", "ck_benchmark_example_results_success_no_failure", "ck_benchmark_example_results_failure_consistency", "ck_benchmark_example_results_exact_match_requires_all", "ck_benchmark_example_results_mismatch_not_exact", "ck_benchmark_example_results_failed_output_invalid"}
    assert {index.name for index in table.indexes} == {"uq_benchmark_example_results_result_example", "ix_benchmark_example_results_result_id", "ix_benchmark_example_results_example_id", "ix_benchmark_example_results_prediction_succeeded", "ix_benchmark_example_results_exact_match", "ix_benchmark_example_results_failure_code"}
    expected = {"benchmark_result_id": ("benchmark_results.id", "CASCADE"), "dataset_example_id": ("dataset_examples.id", "RESTRICT"), "predicted_category_id": ("complaint_categories.id", "RESTRICT"), "predicted_department_id": ("departments.id", "RESTRICT")}
    for name, (target, deletion) in expected.items():
        foreign_key = next(iter(table.c[name].foreign_keys)); assert (foreign_key.target_fullname, foreign_key.ondelete) == (target, deletion)
    assert BenchmarkExampleResult.benchmark_result.property.back_populates == "example_results"
    assert BenchmarkExampleResult.dataset_example.property.back_populates == "benchmark_example_results"


@pytest.mark.parametrize("wrong,cost", [("category", 10), ("department", 2), ("urgency", 1)])
def test_per_example_mismatch_costs(wrong, cost) -> None:
    item = example(); values = {}
    if wrong == "category": values["category"] = uuid4()
    if wrong == "department": values["department"] = uuid4()
    if wrong == "urgency": values["urgency"] = ComplaintUrgency.LOW
    outcome = calculate_benchmark_outcome(example=item, prediction=prediction(item, **values))
    assert outcome.error_cost == cost and not outcome.exact_match


def test_perfect_and_failed_outcomes_are_explicit() -> None:
    item = example(); perfect = calculate_benchmark_outcome(example=item, prediction=prediction(item))
    failed = calculate_benchmark_outcome(example=item, prediction=None, failure_code="predictor_error")
    assert perfect.exact_match and perfect.error_cost == 0 and perfect.prediction_succeeded
    assert failed.error_cost == 13 and not failed.prediction_succeeded and failed.failure_code == "predictor_error"


def test_aggregate_metrics_include_failures_and_nearest_rank_latency() -> None:
    values = [BenchmarkOutcome(str(i), None, None, None, .5, latency, True, True, None, True, True, True, True, 0) for i, latency in enumerate([1, 2, 3, 100])]
    values.append(BenchmarkOutcome("failed", None, None, None, None, None, False, False, "predictor_error", False, False, False, False, 13))
    metrics = aggregate_benchmark_outcomes(list(reversed(values)))
    assert (metrics.sample_count, metrics.failed_prediction_count, metrics.total_error_cost, metrics.weighted_error_cost) == (5, 1, 13, 2.6)
    assert metrics.exact_match_accuracy == metrics.category_accuracy == metrics.department_accuracy == metrics.urgency_accuracy == .8
    assert metrics.structured_output_validity_rate == .8
    assert metrics.average_latency_ms == 26.5 and metrics.p95_latency_ms == 100


@pytest.mark.parametrize("values", [[], [BenchmarkOutcome("x", None, None, None, None, -1, True, True, None, True, True, True, True, 0)], [BenchmarkOutcome("x", None, None, None, float("nan"), 1, True, True, None, True, True, True, True, 0)]])
def test_aggregate_rejects_empty_or_invalid_numeric_values(values) -> None:
    with pytest.raises(InvalidBenchmarkPredictionError): aggregate_benchmark_outcomes(values)


@pytest.mark.anyio
async def test_outcome_repository_is_transaction_neutral() -> None:
    session = MagicMock(); result = MagicMock(); result.scalars.return_value.all.return_value = []; session.execute = AsyncMock(return_value=result)
    repository = BenchmarkExampleResultRepository(session); assert await repository.list_for_result(uuid4()) == []
    session.commit.assert_not_called(); session.rollback.assert_not_called(); session.begin.assert_not_called()


@pytest.mark.anyio
async def test_service_loads_dataset_rows_and_continues_after_prediction_failure() -> None:
    dataset, experiments, results, models, examples, outcomes = (MagicMock() for _ in range(6))
    dataset.get_by_id = AsyncMock(return_value=object()); results.get_for_experiment_and_model = AsyncMock(return_value=None); results.add = AsyncMock(); results.flush = AsyncMock(); results.refresh = AsyncMock(side_effect=lambda value: value)
    version = ModelVersion(id=uuid4(), is_approved=True); models.get_by_id = AsyncMock(return_value=version)
    rows = [DatasetExample(id=uuid4(), example_id="a", title="a", description="a", expected_category_id=uuid4(), expected_department_id=uuid4(), expected_urgency=ComplaintUrgency.HIGH), DatasetExample(id=uuid4(), example_id="b", title="b", description="b", expected_category_id=uuid4(), expected_department_id=uuid4(), expected_urgency=ComplaintUrgency.LOW)]
    examples.list_all_for_dataset = AsyncMock(return_value=rows); outcomes.add = AsyncMock()
    predictor = MagicMock(); predictor.predict_example = AsyncMock(side_effect=[RuntimeError("secret"), prediction(BenchmarkExample("b", "b", "b", rows[1].expected_category_id, rows[1].expected_department_id, rows[1].expected_urgency))])
    service = BenchmarkService(dataset_version_repository=dataset, benchmark_experiment_repository=experiments, benchmark_result_repository=results, model_version_repository=models, predictor_factory=MagicMock(return_value=predictor), dataset_example_repository=examples, benchmark_example_result_repository=outcomes)
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    persisted = await service.run_experiment(experiment=experiment, model_versions=[version])
    assert examples.list_all_for_dataset.await_args.args[0] == experiment.dataset_version_id
    assert outcomes.add.await_count == 2 and persisted[0].failed_prediction_count == 1
    assert persisted[0].accuracy == persisted[0].exact_match_accuracy == Decimal("0.5")
    assert experiment.status is BenchmarkExperimentStatus.COMPLETED


def test_migration_and_api_schema_regression() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini")); revision = script.get_revision("20260805_08")
    assert revision.down_revision == "20260805_07" and script.get_heads() == ["20260805_11"]
    schema = create_app(Settings()).openapi(); properties = schema["components"]["schemas"]["BenchmarkResultResponse"]["properties"]
    assert {"total_error_cost", "exact_match_accuracy", "failed_prediction_count", "category_accuracy", "department_accuracy", "urgency_accuracy", "p95_inference_latency_ms"} <= set(properties)
    assert not any("execute" in path for path in schema["paths"] if "benchmark" in path)
