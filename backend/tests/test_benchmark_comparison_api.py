"""Benchmark comparison schema and REST API tests."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.api.dependencies import (
    get_benchmark_comparison_service,
    get_current_active_user,
    get_transactional_benchmark_comparison_service,
)
from app.api.routes.benchmark_comparisons import (
    create_benchmark_comparison,
    get_benchmark_comparison,
    list_benchmark_comparisons,
)
from app.core.config import Settings
from app.main import create_app
from app.models import BenchmarkExperimentStatus, Role, User
from app.schemas import BenchmarkComparisonCreateRequest, BenchmarkComparisonResponse
from app.services import (
    BenchmarkComparisonNotFoundError,
    BenchmarkComparisonPersistenceError,
    BenchmarkResultNotFoundForComparisonError,
    IncompleteBenchmarkResultError,
    IncompatibleBenchmarkDatasetError,
    InvalidBenchmarkComparisonError,
    MissingBenchmarkMetricsError,
)


NOW = datetime.now(timezone.utc)


def comparison():
    comparison_id, dataset_id, creator_id = uuid4(), uuid4(), uuid4()
    members = []
    for rank in (2, 1):
        result_id, experiment_id, model_id = uuid4(), uuid4(), uuid4()
        benchmark_result = SimpleNamespace(
            id=result_id, benchmark_experiment_id=experiment_id,
            model_version_id=model_id, sample_count=20,
            total_error_cost=Decimal(str(rank)), exact_match_accuracy=Decimal(".9"),
            failed_prediction_count=0, department_accuracy=Decimal(".9"),
            category_accuracy=Decimal(".8"), urgency_accuracy=Decimal(".95"),
            p95_inference_latency_ms=45, average_inference_latency_ms=Decimal("20.5"),
            cost_weighted_error=Decimal(".1"), created_at=NOW,
            model_version=SimpleNamespace(id=model_id, name="router", version=f"v{rank}"),
            experiment=SimpleNamespace(id=experiment_id, name="evaluation", status=BenchmarkExperimentStatus.COMPLETED),
        )
        members.append(SimpleNamespace(
            id=uuid4(), benchmark_comparison_id=comparison_id,
            benchmark_result_id=result_id, rank=rank, created_at=NOW,
            benchmark_result=benchmark_result,
        ))
    return SimpleNamespace(
        id=comparison_id, dataset_version_id=dataset_id, dataset_checksum="sha256",
        dataset_example_count=20, winner_result_id=members[1].benchmark_result_id,
        ranking_metric="deterministic-v1", created_by_user_id=creator_id,
        created_at=NOW, updated_at=NOW, members=members,
    )


def user(role_name="reviewer"):
    value = User(id=uuid4(), role_id=uuid4(), email="user@example.com", password_hash="hash", full_name="User", is_active=True, email_verified=True)
    value.role = Role(id=value.role_id, name=role_name, display_name=role_name.title(), is_active=True)
    return value


def test_request_schema_validation_and_control_field_rejection() -> None:
    identifiers = [uuid4(), uuid4()]
    request = BenchmarkComparisonCreateRequest(benchmark_result_ids=identifiers, ranking_metric="  deterministic-v1  ")
    assert request.benchmark_result_ids == identifiers and request.ranking_metric == "deterministic-v1"
    assert len(BenchmarkComparisonCreateRequest(benchmark_result_ids=[uuid4() for _ in range(10)], ranking_metric="x").benchmark_result_ids) == 10
    invalid = [
        {"benchmark_result_ids": [uuid4()], "ranking_metric": "x"},
        {"benchmark_result_ids": [uuid4() for _ in range(11)], "ranking_metric": "x"},
        {"benchmark_result_ids": [identifiers[0], identifiers[0]], "ranking_metric": "x"},
        {"benchmark_result_ids": ["bad", identifiers[0]], "ranking_metric": "x"},
        {"benchmark_result_ids": identifiers, "ranking_metric": " "},
        {"benchmark_result_ids": identifiers, "ranking_metric": "x" * 101},
        {"benchmark_result_ids": identifiers, "ranking_metric": "x", "extra": 1},
        {"benchmark_result_ids": identifiers, "ranking_metric": "x", "created_by_user_id": uuid4()},
    ]
    for payload in invalid:
        with pytest.raises(ValidationError): BenchmarkComparisonCreateRequest(**payload)


def test_response_validates_nested_typed_metrics_and_orders_members() -> None:
    response = BenchmarkComparisonResponse.model_validate(comparison())
    assert [member.rank for member in response.members] == [1, 2]
    assert response.members[0].benchmark_result.total_error_cost == Decimal("1")
    assert response.members[0].benchmark_result.model_version.name == "router"
    assert response.members[0].benchmark_result.experiment.status is BenchmarkExperimentStatus.COMPLETED


@pytest.mark.anyio
async def test_direct_routes_delegate_creator_values_and_pagination() -> None:
    value, current_user, service = comparison(), user(), MagicMock()
    service.create_comparison = AsyncMock(return_value=value)
    service.get_comparison = AsyncMock(return_value=value)
    service.list_comparisons = AsyncMock(return_value=[value])
    payload = BenchmarkComparisonCreateRequest(benchmark_result_ids=[uuid4(), uuid4()], ranking_metric=" metric ")
    created = await create_benchmark_comparison(payload, current_user, service)
    delegated = service.create_comparison.await_args.args[0]
    assert delegated.benchmark_result_ids == payload.benchmark_result_ids
    assert delegated.ranking_metric == "metric" and delegated.created_by_user_id == current_user.id
    assert [member.rank for member in created.members] == [1, 2]
    assert (await get_benchmark_comparison(value.id, current_user, service)).id == value.id
    listed = await list_benchmark_comparisons(current_user, service, 3, 7)
    assert (listed.offset, listed.limit, listed.count) == (3, 7, 1)
    service.get_comparison.assert_awaited_once_with(value.id)
    service.list_comparisons.assert_awaited_once_with(offset=3, limit=7)


@pytest.mark.anyio
@pytest.mark.parametrize("error,code,detail", [
    (BenchmarkResultNotFoundForComparisonError("secret"), 404, "Benchmark result not found"),
    (InvalidBenchmarkComparisonError("secret"), 422, "Invalid benchmark comparison"),
    (IncompleteBenchmarkResultError("secret"), 409, "Benchmark result is not complete"),
    (MissingBenchmarkMetricsError("secret"), 409, "Benchmark result metrics are incomplete"),
    (IncompatibleBenchmarkDatasetError("secret"), 409, "Benchmark results use incompatible datasets"),
    (BenchmarkComparisonPersistenceError("secret SQL"), 500, "Benchmark comparison could not be persisted"),
])
async def test_create_error_mapping_is_safe(error, code, detail) -> None:
    service = MagicMock(); service.create_comparison = AsyncMock(side_effect=error)
    payload = BenchmarkComparisonCreateRequest(benchmark_result_ids=[uuid4(), uuid4()], ranking_metric="metric")
    with pytest.raises(HTTPException) as caught: await create_benchmark_comparison(payload, user(), service)
    assert (caught.value.status_code, caught.value.detail) == (code, detail)
    assert "secret" not in str(caught.value)


@pytest.mark.anyio
async def test_get_missing_maps_to_safe_404() -> None:
    service = MagicMock(); service.get_comparison = AsyncMock(side_effect=BenchmarkComparisonNotFoundError("secret"))
    with pytest.raises(HTTPException) as caught: await get_benchmark_comparison(uuid4(), user(), service)
    assert (caught.value.status_code, caught.value.detail) == (404, "Benchmark comparison not found")


@pytest.mark.anyio
async def test_integration_routes_validation_and_creator_derivation() -> None:
    app, value, current_user, service = create_app(Settings()), comparison(), user(), MagicMock()
    service.create_comparison = AsyncMock(return_value=value); service.get_comparison = AsyncMock(return_value=value); service.list_comparisons = AsyncMock(return_value=[value])
    app.dependency_overrides[get_current_active_user] = lambda: current_user
    app.dependency_overrides[get_benchmark_comparison_service] = lambda: service
    app.dependency_overrides[get_transactional_benchmark_comparison_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    payload = {"benchmark_result_ids": [str(uuid4()), str(uuid4())], "ranking_metric": " metric "}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        post = await client.post("/api/benchmark-comparisons", json=payload)
        get = await client.get(f"/api/benchmark-comparisons/{value.id}")
        listed = await client.get("/api/benchmark-comparisons")
        invalid = await client.post("/api/benchmark-comparisons", json={"benchmark_result_ids": [payload["benchmark_result_ids"][0]] * 2, "ranking_metric": "x"})
        bad_id = await client.get("/api/benchmark-comparisons/not-a-uuid")
    assert (post.status_code, get.status_code, listed.status_code) == (201, 200, 200)
    assert invalid.status_code == bad_id.status_code == 422
    assert [member["rank"] for member in post.json()["members"]] == [1, 2]
    assert "total_error_cost" in post.json()["members"][0]["benchmark_result"]
    assert service.create_comparison.await_args.args[0].created_by_user_id == current_user.id
    service.list_comparisons.assert_awaited_once_with(offset=0, limit=100)


@pytest.mark.anyio
@pytest.mark.parametrize("role_name,expected", [("reviewer", 200), ("administrator", 200), ("customer", 403)])
async def test_all_routes_use_reviewer_or_administrator(role_name, expected) -> None:
    app, value, service = create_app(Settings()), comparison(), MagicMock()
    service.create_comparison = AsyncMock(return_value=value); service.get_comparison = AsyncMock(return_value=value); service.list_comparisons = AsyncMock(return_value=[value])
    app.dependency_overrides[get_current_active_user] = lambda: user(role_name)
    app.dependency_overrides[get_benchmark_comparison_service] = lambda: service
    app.dependency_overrides[get_transactional_benchmark_comparison_service] = lambda: service
    transport = httpx.ASGITransport(app=app); body = {"benchmark_result_ids": [str(uuid4()), str(uuid4())], "ranking_metric": "x"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        statuses = [(await client.post("/api/benchmark-comparisons", json=body)).status_code, (await client.get("/api/benchmark-comparisons")).status_code, (await client.get(f"/api/benchmark-comparisons/{value.id}")).status_code]
    assert statuses == [201 if expected == 200 else expected, expected, expected]


@pytest.mark.anyio
async def test_unauthenticated_routes_return_401() -> None:
    app = create_app(Settings()); service = MagicMock()
    app.dependency_overrides[get_benchmark_comparison_service] = lambda: service
    app.dependency_overrides[get_transactional_benchmark_comparison_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [await client.get("/api/benchmark-comparisons"), await client.get(f"/api/benchmark-comparisons/{uuid4()}"), await client.post("/api/benchmark-comparisons", json={})]
    assert [response.status_code for response in responses] == [401, 401, 401]
