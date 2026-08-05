"""Benchmark REST API foundation tests."""

from datetime import datetime, timezone
from decimal import Decimal
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from pydantic import ValidationError
import pytest

from app.api.dependencies import (
    get_benchmark_experiment_repository,
    get_benchmark_predictor_factory,
    get_benchmark_result_repository,
    get_benchmark_service,
    get_dataset_version_repository,
    get_transactional_benchmark_experiment_repository,
    get_transactional_benchmark_result_repository,
    get_transactional_benchmark_service,
    get_transactional_dataset_version_repository,
)
from app.api.routes.benchmarks import (
    create_benchmark_experiment,
    get_benchmark_experiment,
    get_benchmark_result,
    list_dataset_experiments,
    list_experiment_results,
)
from app.core.config import Settings
from app.main import create_app
from app.models import BenchmarkExperiment, BenchmarkExperimentStatus, BenchmarkResult, User
from app.schemas import BenchmarkExperimentCreateRequest, BenchmarkExperimentResponse, BenchmarkResultResponse
from app.services import BenchmarkExperimentNotFoundError, BenchmarkResultNotFoundError


NOW = datetime.now(timezone.utc)


def experiment(**overrides):
    values = dict(id=uuid4(), dataset_version_id=uuid4(), name="Benchmark", status=BenchmarkExperimentStatus.PENDING, configuration={}, started_at=None, completed_at=None, failure_message=None, created_at=NOW)
    values.update(overrides)
    return BenchmarkExperiment(**values)


def result():
    return BenchmarkResult(id=uuid4(), benchmark_experiment_id=uuid4(), model_version_id=uuid4(), sample_count=2, accuracy=Decimal(".5"), macro_precision=None, macro_recall=None, macro_f1=Decimal(".5"), cost_weighted_error=Decimal("2"), structured_output_validity_rate=Decimal("1"), average_inference_latency_ms=Decimal("4"), throughput_per_second=None, estimated_cost=None, per_class_metrics=None, additional_metrics={"safe": 1}, created_at=NOW)


def test_creation_schema_is_trimmed_bounded_json_and_forbids_control_fields() -> None:
    identifier = uuid4()
    request = BenchmarkExperimentCreateRequest(dataset_version_id=identifier, name="  Trial  ")
    assert request.name == "Trial" and request.configuration == {}
    for payload in [
        {"dataset_version_id": identifier, "name": " "},
        {"dataset_version_id": identifier, "name": "x" * 201},
        {"dataset_version_id": identifier, "name": "ok", "status": "completed"},
        {"dataset_version_id": identifier, "name": "ok", "configuration": {"bad": float("nan")}},
    ]:
        with pytest.raises(ValidationError): BenchmarkExperimentCreateRequest(**payload)


def test_safe_response_schemas_exclude_internal_fields() -> None:
    experiment_fields = BenchmarkExperimentResponse.model_validate(experiment()).model_dump()
    result_fields = BenchmarkResultResponse.model_validate(result()).model_dump()
    assert "results" not in experiment_fields and "_sa_instance_state" not in experiment_fields
    for unsafe in ("examples", "configuration", "raw_output", "complaint_text", "_sa_instance_state"):
        assert unsafe not in result_fields


@pytest.mark.anyio
async def test_create_uses_exact_dataset_and_repository_and_pending_status() -> None:
    dataset_id = uuid4()
    payload = BenchmarkExperimentCreateRequest(dataset_version_id=dataset_id, name="  Run  ", configuration={"seed": 7})
    datasets = MagicMock(); datasets.get_by_id = AsyncMock(return_value=object())
    repositories = MagicMock(); repositories.add = AsyncMock(); repositories.flush = AsyncMock()
    refreshed = experiment(dataset_version_id=dataset_id, name="Run", configuration={"seed": 7})
    repositories.refresh = AsyncMock(return_value=refreshed)
    created = await create_benchmark_experiment(payload, User(id=uuid4()), datasets, repositories)
    datasets.get_by_id.assert_awaited_once_with(dataset_id)
    persisted = repositories.add.await_args.args[0]
    assert persisted.status is BenchmarkExperimentStatus.PENDING
    assert (persisted.name, persisted.configuration) == ("Run", {"seed": 7})
    repositories.flush.assert_awaited_once(); repositories.refresh.assert_awaited_once_with(persisted)
    assert created.id == refreshed.id
    assert not repositories.commit.called and not repositories.rollback.called and not repositories.begin.called


@pytest.mark.anyio
async def test_create_missing_dataset_is_generic_404() -> None:
    datasets = MagicMock(); datasets.get_by_id = AsyncMock(return_value=None)
    repository = MagicMock(); repository.add = AsyncMock()
    with pytest.raises(Exception) as caught:
        await create_benchmark_experiment(BenchmarkExperimentCreateRequest(dataset_version_id=uuid4(), name="Run"), User(id=uuid4()), datasets, repository)
    assert caught.value.status_code == 404 and caught.value.detail == "Dataset version not found"
    repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_read_routes_delegate_and_translate_missing() -> None:
    item, evidence, user = experiment(), result(), User(id=uuid4())
    service = MagicMock()
    service.get_experiment = AsyncMock(return_value=item); service.get_result = AsyncMock(return_value=evidence)
    assert (await get_benchmark_experiment(item.id, user, service)).id == item.id
    assert (await get_benchmark_result(evidence.id, user, service)).id == evidence.id
    service.get_experiment.side_effect = BenchmarkExperimentNotFoundError("secret")
    with pytest.raises(Exception) as missing_experiment:
        await get_benchmark_experiment(uuid4(), user, service)
    assert (missing_experiment.value.status_code, missing_experiment.value.detail) == (404, "Benchmark experiment not found")
    service.get_result.side_effect = BenchmarkResultNotFoundError("secret")
    with pytest.raises(Exception) as missing_result:
        await get_benchmark_result(uuid4(), user, service)
    assert (missing_result.value.status_code, missing_result.value.detail) == (404, "Benchmark result not found")


@pytest.mark.anyio
async def test_lists_delegate_exact_pagination_and_count_returned_items() -> None:
    item, evidence, user, service = experiment(), result(), User(id=uuid4()), MagicMock()
    service.list_dataset_experiments = AsyncMock(return_value=[item])
    service.list_experiment_results = AsyncMock(return_value=[evidence])
    listed = await list_dataset_experiments(item.dataset_version_id, user, service, 2, 5)
    results = await list_experiment_results(item.id, user, service, 3, 7)
    assert (listed.offset, listed.limit, listed.count) == (2, 5, 1)
    assert (results.offset, results.limit, results.count) == (3, 7, 1)
    service.list_dataset_experiments.assert_awaited_once_with(dataset_version_id=item.dataset_version_id, offset=2, limit=5)
    service.list_experiment_results.assert_awaited_once_with(experiment_id=item.id, offset=3, limit=7)


@pytest.mark.anyio
async def test_repository_and_service_dependencies_are_exact_and_neutral() -> None:
    session = MagicMock()
    read = [await function(session) for function in (get_dataset_version_repository, get_benchmark_experiment_repository, get_benchmark_result_repository)]
    transactional = [await function(session) for function in (get_transactional_dataset_version_repository, get_transactional_benchmark_experiment_repository, get_transactional_benchmark_result_repository)]
    assert all(repository.session is session for repository in read + transactional)
    factory_one, factory_two = get_benchmark_predictor_factory(), get_benchmark_predictor_factory()
    assert factory_one is not factory_two
    dependencies = [MagicMock() for _ in range(5)]
    assert get_benchmark_service(*dependencies) is not get_transactional_benchmark_service(*dependencies)
    assert session.mock_calls == []


def test_openapi_benchmark_contract_is_safe_and_exact() -> None:
    schema = create_app(Settings()).openapi()
    paths = schema["paths"]
    expected = {
        "/api/benchmarks/experiments",
        "/api/benchmarks/datasets/{dataset_version_id}/experiments",
        "/api/benchmarks/experiments/{experiment_id}/results",
        "/api/benchmarks/experiments/{experiment_id}",
        "/api/benchmarks/results/{result_id}",
    }
    assert expected <= paths.keys()
    assert "post" in paths["/api/benchmarks/experiments"]
    assert all("Benchmarks" in operation["tags"] for path in expected for operation in paths[path].values() if isinstance(operation, dict) and "tags" in operation)
    request_fields = schema["components"]["schemas"]["BenchmarkExperimentCreateRequest"]["properties"]
    result_fields = schema["components"]["schemas"]["BenchmarkResultResponse"]["properties"]
    assert "status" not in request_fields and "raw_output" not in result_fields
    assert not any("/run" in path or "upload" in path for path in paths if "benchmark" in path)
