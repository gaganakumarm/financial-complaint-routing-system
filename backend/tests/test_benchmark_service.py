"""Benchmark service tests without database connections."""

import asyncio
from copy import deepcopy
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.benchmark import BenchmarkExample, BenchmarkPrediction
from app.models import BenchmarkExperiment, BenchmarkExperimentStatus, ModelType, ModelVersion, ComplaintUrgency
from app.services import (
    BenchmarkExecutionError, BenchmarkExperimentNotFoundError,
    BenchmarkPersistenceError, BenchmarkResultNotFoundError, BenchmarkService,
    DuplicateBenchmarkResultError, ModelVersionNotFoundError,
)


def example():
    return BenchmarkExample("one", "safe title", "safe description", uuid4(), uuid4(), ComplaintUrgency.MEDIUM)


def service_setup():
    dataset, experiments, results, models = (MagicMock() for _ in range(4))
    for repo in (dataset, experiments, results, models):
        repo.get_by_id = AsyncMock()
        repo.add = AsyncMock(); repo.flush = AsyncMock(); repo.refresh = AsyncMock()
        repo.commit = AsyncMock(); repo.rollback = AsyncMock(); repo.begin = AsyncMock()
    dataset.get_by_id.return_value = object()
    models.get_by_id.side_effect = lambda value: ModelVersion(id=value, is_approved=True)
    results.get_for_experiment_and_model = AsyncMock(return_value=None)
    results.add = AsyncMock(); results.flush = AsyncMock(); results.refresh = AsyncMock(side_effect=lambda value: value)
    predictor = MagicMock()
    predictor.predict_example = AsyncMock(side_effect=lambda **kwargs: BenchmarkPrediction(kwargs["example"].example_id, kwargs["example"].expected_category_id, kwargs["example"].expected_department_id, kwargs["example"].expected_urgency, .75, 4))
    factory = MagicMock(return_value=predictor)
    service = BenchmarkService(dataset_version_repository=dataset, benchmark_experiment_repository=experiments, benchmark_result_repository=results, model_version_repository=models, predictor_factory=factory)
    return service, dataset, experiments, results, models, factory, predictor


@pytest.mark.anyio
async def test_multiple_models_persist_in_order_and_complete_neutrally() -> None:
    service, dataset, _, results, models, factory, predictor = service_setup()
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    versions = [ModelVersion(id=uuid4(), is_approved=True, model_type=ModelType.TFIDF_CLASSIFIER), ModelVersion(id=uuid4(), is_approved=True, model_type=ModelType.HYBRID)]
    authoritative = [
        ModelVersion(id=versions[0].id, is_approved=True, model_type=ModelType.TFIDF_CLASSIFIER),
        ModelVersion(id=versions[1].id, is_approved=True, model_type=ModelType.HYBRID),
    ]
    models.get_by_id.side_effect = authoritative
    snapshots = [
        deepcopy({key: value for key, value in item.__dict__.items() if key != "_sa_instance_state"})
        for item in versions
    ]
    persisted = await service.run_experiment(experiment=experiment, examples=[example()], model_versions=versions)
    assert experiment.status is BenchmarkExperimentStatus.COMPLETED
    assert experiment.started_at and experiment.completed_at
    assert [item.model_version_id for item in persisted] == [item.id for item in versions]
    assert [call.args[0] for call in factory.call_args_list] == authoritative
    assert [call.kwargs["model_version"] for call in predictor.predict_example.await_args_list] == authoritative
    assert predictor.predict_example.await_count == 2
    assert results.add.await_count == results.flush.await_count == results.refresh.await_count == 2
    assert [
        {key: value for key, value in item.__dict__.items() if key != "_sa_instance_state"}
        for item in versions
    ] == snapshots
    for repo in (dataset, service._benchmark_experiment_repository, results, models):
        repo.commit.assert_not_awaited(); repo.rollback.assert_not_awaited(); repo.begin.assert_not_awaited()


@pytest.mark.anyio
async def test_duplicate_prevents_prediction_and_completion() -> None:
    service, _, _, results, models, factory, predictor = service_setup()
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    version = ModelVersion(id=uuid4(), is_approved=True)
    models.get_by_id.side_effect = [ModelVersion(id=version.id, is_approved=True)]
    results.get_for_experiment_and_model.return_value = object()
    with pytest.raises(DuplicateBenchmarkResultError): await service.run_experiment(experiment=experiment, examples=[example()], model_versions=[version])
    factory.assert_not_called(); predictor.predict_example.assert_not_awaited(); results.add.assert_not_awaited()
    assert experiment.status is BenchmarkExperimentStatus.PENDING


@pytest.mark.anyio
async def test_predictor_failure_becomes_failed_outcome_and_continues() -> None:
    service, _, _, _, _, _, predictor = service_setup()
    predictor.predict_example.side_effect = RuntimeError("secret title credential")
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    version = ModelVersion(id=uuid4(), is_approved=True)
    service._model_version_repository.get_by_id.side_effect = [
        ModelVersion(id=version.id, is_approved=True)
    ]
    persisted = await service.run_experiment(experiment=experiment, examples=[example()], model_versions=[version])
    assert persisted[0].failed_prediction_count == 1
    assert persisted[0].total_error_cost == 13
    assert experiment.status is BenchmarkExperimentStatus.COMPLETED


@pytest.mark.anyio
async def test_reads_delegate_and_translate_missing() -> None:
    service, _, experiments, results, _, _, _ = service_setup()
    experiment, result = object(), object()
    experiments.get_by_id.return_value = experiment; results.get_by_id.return_value = result
    assert await service.get_experiment(uuid4()) is experiment
    assert await service.get_result(uuid4()) is result
    experiments.get_by_id.return_value = None; results.get_by_id.return_value = None
    with pytest.raises(BenchmarkExperimentNotFoundError): await service.get_experiment(uuid4())
    with pytest.raises(BenchmarkResultNotFoundError): await service.get_result(uuid4())
    experiments.list_for_dataset = AsyncMock(return_value=[experiment])
    assert await service.list_dataset_experiments(dataset_version_id=uuid4(), offset=2, limit=5) == [experiment]


@pytest.mark.anyio
async def test_repository_models_are_authoritative_and_all_preflight_precedes_factory() -> None:
    service, _, _, results, models, factory, predictor = service_setup()
    requested = [
        ModelVersion(id=uuid4(), is_approved=True, configuration={"credential": "caller-secret"}),
        ModelVersion(id=uuid4(), is_approved=False, configuration={"credential": "caller-secret"}),
    ]
    authoritative = [
        ModelVersion(id=requested[0].id, is_approved=True, configuration={"safe": 1}),
        ModelVersion(id=requested[1].id, is_approved=True, configuration={"safe": 2}),
    ]
    models.get_by_id.side_effect = authoritative
    def factory_after_preflight(version):
        assert results.get_for_experiment_and_model.await_count == 2
        return predictor
    factory.side_effect = factory_after_preflight
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    persisted = await service.run_experiment(experiment=experiment, examples=[example()], model_versions=requested)
    assert [call.args[0] for call in factory.call_args_list] == authoritative
    assert [call.kwargs["model_version"] for call in predictor.predict_example.await_args_list] == authoritative
    assert [item.model_version_id for item in persisted] == [item.id for item in authoritative]
    assert results.get_for_experiment_and_model.await_count == 2
    assert all("caller-secret" not in json.dumps(item.additional_metrics) for item in persisted)
    json.dumps([item.additional_metrics for item in persisted])


@pytest.mark.anyio
async def test_second_model_failure_leaves_prior_flush_for_caller_rollback() -> None:
    service, _, experiments, results, models, factory, _ = service_setup()
    requested = [ModelVersion(id=uuid4()), ModelVersion(id=uuid4())]
    authoritative = [ModelVersion(id=item.id, is_approved=True) for item in requested]
    models.get_by_id.side_effect = authoritative
    first_predictor = MagicMock()
    first_item = example()
    first_predictor.predict_example = AsyncMock(return_value=BenchmarkPrediction(
        first_item.example_id, first_item.expected_category_id,
        first_item.expected_department_id, first_item.expected_urgency, .5, 1
    ))
    second_predictor = MagicMock()
    second_predictor.predict_example = AsyncMock(side_effect=RuntimeError("secret"))
    factory.side_effect = [first_predictor, second_predictor]
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    persisted = await service.run_experiment(experiment=experiment, examples=[first_item], model_versions=requested)
    assert experiment.status is BenchmarkExperimentStatus.COMPLETED
    assert persisted[1].failed_prediction_count == 1
    assert results.add.await_count == 2; assert results.flush.await_count == 2
    for repo in (service._dataset_version_repository, experiments, results, models):
        repo.commit.assert_not_awaited(); repo.rollback.assert_not_awaited(); repo.begin.assert_not_awaited()


@pytest.mark.anyio
async def test_invalid_prediction_becomes_failed_outcome() -> None:
    service, _, _, _, models, _, predictor = service_setup()
    requested = ModelVersion(id=uuid4())
    models.get_by_id.side_effect = [ModelVersion(id=requested.id, is_approved=True)]
    predictor.predict_example.return_value = object()
    predictor.predict_example.side_effect = None
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    persisted = await service.run_experiment(experiment=experiment, examples=[example()], model_versions=[requested])
    assert persisted[0].failed_prediction_count == 1
    assert experiment.status is BenchmarkExperimentStatus.COMPLETED


@pytest.mark.anyio
async def test_unapproved_authoritative_model_is_rejected_before_mutation() -> None:
    service, _, _, results, models, factory, _ = service_setup()
    requested = ModelVersion(id=uuid4(), is_approved=True, configuration={"fake": True})
    models.get_by_id.side_effect = [ModelVersion(id=requested.id, is_approved=False)]
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    with pytest.raises(ModelVersionNotFoundError):
        await service.run_experiment(experiment=experiment, examples=[example()], model_versions=[requested])
    assert experiment.status is BenchmarkExperimentStatus.PENDING
    factory.assert_not_called(); results.add.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["factory"])
async def test_execution_failures_are_generic(stage) -> None:
    service, _, _, _, models, factory, predictor = service_setup()
    requested = ModelVersion(id=uuid4(), is_approved=True)
    models.get_by_id.side_effect = [ModelVersion(id=requested.id, is_approved=True)]
    if stage == "factory": factory.side_effect = RuntimeError("credential configuration-secret")
    else: predictor.predict_example.side_effect = RuntimeError("safe title safe description")
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    with pytest.raises(BenchmarkExecutionError) as caught:
        await service.run_experiment(experiment=experiment, examples=[example()], model_versions=[requested])
    assert str(caught.value) == experiment.failure_message == "Benchmark execution failed."
    assert experiment.status is BenchmarkExperimentStatus.FAILED and experiment.completed_at


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["add", "flush", "refresh"])
async def test_persistence_failures_are_generic(operation) -> None:
    service, _, _, results, models, _, _ = service_setup()
    requested = ModelVersion(id=uuid4(), is_approved=True)
    models.get_by_id.side_effect = [ModelVersion(id=requested.id, is_approved=True)]
    getattr(results, operation).side_effect = RuntimeError("database credential secret")
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    with pytest.raises(BenchmarkPersistenceError) as caught:
        await service.run_experiment(experiment=experiment, examples=[example()], model_versions=[requested])
    assert str(caught.value) == "Benchmark result persistence failed."
    assert experiment.status is BenchmarkExperimentStatus.FAILED
    results.commit.assert_not_awaited(); results.rollback.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["factory", "prediction", "persistence"])
async def test_cancellation_marks_cancelled_and_propagates(stage) -> None:
    service, _, _, results, models, factory, predictor = service_setup()
    requested = ModelVersion(id=uuid4(), is_approved=True)
    models.get_by_id.side_effect = [ModelVersion(id=requested.id, is_approved=True)]
    if stage == "factory": factory.side_effect = asyncio.CancelledError()
    elif stage == "prediction": predictor.predict_example.side_effect = asyncio.CancelledError()
    else: results.add.side_effect = asyncio.CancelledError()
    experiment = BenchmarkExperiment(id=uuid4(), dataset_version_id=uuid4(), status=BenchmarkExperimentStatus.PENDING, configuration={})
    with pytest.raises(asyncio.CancelledError):
        await service.run_experiment(experiment=experiment, examples=[example()], model_versions=[requested])
    assert experiment.status is BenchmarkExperimentStatus.CANCELLED
    assert experiment.completed_at and experiment.failure_message is None


@pytest.mark.anyio
async def test_result_listing_slices_and_validates_without_mutation() -> None:
    service, _, experiments, results, models, _, _ = service_setup()
    values = [object() for _ in range(5)]
    results.list_for_experiment = AsyncMock(return_value=values)
    identifier = uuid4()
    assert await service.list_experiment_results(experiment_id=identifier, offset=0, limit=2) == values[:2]
    assert await service.list_experiment_results(experiment_id=identifier, offset=9, limit=2) == []
    for offset, limit in [(-1, 1), (0, 0), (0, 501)]:
        with pytest.raises(ValueError):
            await service.list_experiment_results(experiment_id=identifier, offset=offset, limit=limit)
    for repo in (service._dataset_version_repository, experiments, results, models):
        repo.add.assert_not_awaited(); repo.flush.assert_not_awaited(); repo.refresh.assert_not_awaited()
        repo.commit.assert_not_awaited(); repo.rollback.assert_not_awaited(); repo.begin.assert_not_awaited()


@pytest.mark.anyio
async def test_dataset_listing_delegates_pagination_policy_exactly() -> None:
    service, _, experiments, _, _, _, _ = service_setup()
    identifier = uuid4()
    experiments.list_for_dataset = AsyncMock(return_value=[])
    assert await service.list_dataset_experiments(dataset_version_id=identifier, offset=4, limit=9) == []
    experiments.list_for_dataset.assert_awaited_once_with(identifier, offset=4, limit=9)
    experiments.list_for_dataset.side_effect = ValueError("invalid pagination")
    with pytest.raises(ValueError, match="invalid pagination"):
        await service.list_dataset_experiments(dataset_version_id=identifier, offset=-1, limit=9)
