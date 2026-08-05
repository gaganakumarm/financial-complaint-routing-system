"""Model-promotion schema, route, and authorization tests."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.api.dependencies import get_current_active_user, get_model_promotion_service, get_transactional_model_promotion_service
from app.api.routes.model_promotions import approve_model_promotion, cancel_model_promotion, create_model_promotion, get_model_promotion, list_model_promotions, reject_model_promotion
from app.core.config import Settings
from app.main import create_app
from app.models import ModelPromotionStatus, Role, User
from app.schemas import ModelPromotionCancelRequest, ModelPromotionCreateRequest, ModelPromotionResponse, ModelPromotionReviewRequest
from app.services import BenchmarkComparisonNotFoundForPromotionError, BenchmarkResultModelMismatchError, BenchmarkResultNotFoundForPromotionError, BenchmarkResultNotInComparisonError, DuplicatePendingModelPromotionError, InvalidModelPromotionError, ModelPromotionNotFoundError, ModelPromotionPersistenceError, ModelPromotionStateConflictError, NonWinningResultRequiresOverrideError


NOW = datetime.now(timezone.utc)


def promotion(*, terminal=False):
    comparison_id, result_id, model_id, requester_id = uuid4(), uuid4(), uuid4(), uuid4()
    reviewer_id = uuid4() if terminal else None
    return SimpleNamespace(
        id=uuid4(), benchmark_comparison_id=comparison_id,
        selected_benchmark_result_id=result_id, selected_model_version_id=model_id,
        status=ModelPromotionStatus.APPROVED if terminal else ModelPromotionStatus.PENDING,
        rationale="Strong evidence", override_winner=False,
        requested_by_user_id=requester_id, reviewed_by_user_id=reviewer_id,
        requested_at=NOW, reviewed_at=NOW if terminal else None,
        review_note="Approved" if terminal else None, created_at=NOW, updated_at=NOW,
        benchmark_comparison=SimpleNamespace(id=comparison_id, dataset_version_id=uuid4(), winner_result_id=result_id, ranking_metric="deterministic-v1", created_at=NOW),
        selected_benchmark_result=SimpleNamespace(id=result_id, benchmark_experiment_id=uuid4(), model_version_id=model_id, sample_count=20, total_error_cost=Decimal("2"), exact_match_accuracy=Decimal(".9"), failed_prediction_count=0, department_accuracy=Decimal(".9"), category_accuracy=Decimal(".8"), urgency_accuracy=Decimal(".95"), p95_inference_latency_ms=50, average_inference_latency_ms=Decimal("20.5"), cost_weighted_error=Decimal(".1"), created_at=NOW),
        selected_model_version=SimpleNamespace(id=model_id, name="router", version="v1"),
        requested_by_user=SimpleNamespace(id=requester_id, email="requester@example.com", full_name="Requester"),
        reviewed_by_user=SimpleNamespace(id=reviewer_id, email="admin@example.com", full_name="Admin") if terminal else None,
    )


def user(role_name="reviewer"):
    value = User(id=uuid4(), role_id=uuid4(), email="user@example.com", password_hash="secret", full_name="User", is_active=True, email_verified=True)
    value.role = Role(id=value.role_id, name=role_name, display_name=role_name.title(), is_active=True)
    return value


def test_request_schemas_trim_validate_strictly_and_forbid_control_fields() -> None:
    ids = (uuid4(), uuid4())
    request = ModelPromotionCreateRequest(benchmark_comparison_id=ids[0], selected_benchmark_result_id=ids[1], rationale="  evidence  ", override_winner=True)
    assert request.rationale == "evidence" and request.override_winner is True
    invalid = [
        {"benchmark_comparison_id": ids[0], "selected_benchmark_result_id": ids[1], "rationale": " "},
        {"benchmark_comparison_id": ids[0], "selected_benchmark_result_id": ids[1], "rationale": "x" * 10001},
        {"benchmark_comparison_id": ids[0], "selected_benchmark_result_id": ids[1], "rationale": "x", "override_winner": 1},
    ]
    for field in ("requested_by_user_id", "selected_model_version_id", "status", "review_note", "requested_at"):
        invalid.append({"benchmark_comparison_id": ids[0], "selected_benchmark_result_id": ids[1], "rationale": "x", field: "unexpected"})
    for payload in invalid:
        with pytest.raises(ValidationError): ModelPromotionCreateRequest(**payload)
    assert ModelPromotionReviewRequest(review_note="  reviewed  ").review_note == "reviewed"
    assert ModelPromotionCancelRequest(cancellation_note="  withdrawn  ").cancellation_note == "withdrawn"
    for schema, field in ((ModelPromotionReviewRequest, "review_note"), (ModelPromotionCancelRequest, "cancellation_note")):
        for payload in ({field: " "}, {field: "x" * 10001}, {field: "ok", "extra": 1}):
            with pytest.raises(ValidationError): schema(**payload)


def test_response_supports_pending_terminal_nested_metrics_and_safe_users() -> None:
    pending = ModelPromotionResponse.model_validate(promotion())
    terminal = ModelPromotionResponse.model_validate(promotion(terminal=True))
    assert pending.reviewed_by_user is None and pending.reviewed_at is None
    assert terminal.reviewed_by_user is not None and terminal.review_note == "Approved"
    assert pending.selected_benchmark_result.total_error_cost == Decimal("2")
    assert set(pending.requested_by_user.model_dump()) == {"id", "email", "full_name"}


@pytest.mark.anyio
async def test_direct_routes_delegate_authenticated_ids_and_pagination() -> None:
    value, current_user, service = promotion(), user(), MagicMock()
    service.create_promotion = AsyncMock(return_value=value); service.get_promotion = AsyncMock(return_value=value); service.list_promotions = AsyncMock(return_value=[value])
    service.approve_promotion = AsyncMock(return_value=value); service.reject_promotion = AsyncMock(return_value=value); service.cancel_promotion = AsyncMock(return_value=value)
    payload = ModelPromotionCreateRequest(benchmark_comparison_id=value.benchmark_comparison_id, selected_benchmark_result_id=value.selected_benchmark_result_id, rationale=" evidence ", override_winner=True)
    assert (await create_model_promotion(payload, current_user, service)).id == value.id
    delegated = service.create_promotion.await_args.args[0]
    assert delegated.requested_by_user_id == current_user.id and delegated.rationale == "evidence" and delegated.override_winner is True
    assert (await get_model_promotion(value.id, current_user, service)).id == value.id
    listed = await list_model_promotions(current_user, service, ModelPromotionStatus.PENDING, 3, 7)
    assert (listed.offset, listed.limit, listed.count) == (3, 7, 1)
    service.list_promotions.assert_awaited_once_with(status=ModelPromotionStatus.PENDING, offset=3, limit=7)
    note = ModelPromotionReviewRequest(review_note=" reviewed ")
    await approve_model_promotion(value.id, note, current_user, service); await reject_model_promotion(value.id, note, current_user, service)
    assert service.approve_promotion.await_args.args[0].reviewed_by_user_id == current_user.id
    assert service.reject_promotion.await_args.args[0].review_note == "reviewed"
    await cancel_model_promotion(value.id, ModelPromotionCancelRequest(cancellation_note=" withdrawn "), current_user, service)
    assert service.cancel_promotion.await_args.args[0].cancelled_by_user_id == current_user.id


@pytest.mark.anyio
@pytest.mark.parametrize("error,code,detail", [
    (ModelPromotionNotFoundError("secret"), 404, "Model promotion not found"),
    (BenchmarkComparisonNotFoundForPromotionError("secret"), 404, "Benchmark comparison not found"),
    (BenchmarkResultNotFoundForPromotionError("secret"), 404, "Benchmark result not found"),
    (InvalidModelPromotionError("secret"), 422, "Invalid model promotion"),
    (BenchmarkResultNotInComparisonError("secret"), 409, "Benchmark result does not belong to the comparison"),
    (BenchmarkResultModelMismatchError("secret"), 409, "Benchmark result and model version do not match"),
    (NonWinningResultRequiresOverrideError("secret"), 409, "Selecting a non-winning result requires an override"),
    (DuplicatePendingModelPromotionError("secret"), 409, "A pending model promotion already exists for this comparison"),
    (ModelPromotionStateConflictError("secret"), 409, "Model promotion state does not allow this operation"),
    (ModelPromotionPersistenceError("secret SQL"), 500, "Model promotion could not be persisted"),
])
async def test_create_error_mapping_is_exact_and_safe(error, code, detail) -> None:
    service = MagicMock(); service.create_promotion = AsyncMock(side_effect=error)
    payload = ModelPromotionCreateRequest(benchmark_comparison_id=uuid4(), selected_benchmark_result_id=uuid4(), rationale="evidence")
    with pytest.raises(HTTPException) as caught: await create_model_promotion(payload, user(), service)
    assert (caught.value.status_code, caught.value.detail) == (code, detail) and "secret" not in str(caught.value)


@pytest.mark.anyio
async def test_get_and_transition_errors_map_safely() -> None:
    service = MagicMock(); service.get_promotion = AsyncMock(side_effect=ModelPromotionNotFoundError("secret"))
    with pytest.raises(HTTPException) as caught: await get_model_promotion(uuid4(), user(), service)
    assert (caught.value.status_code, caught.value.detail) == (404, "Model promotion not found")
    service.approve_promotion = AsyncMock(side_effect=ModelPromotionStateConflictError("secret"))
    with pytest.raises(HTTPException) as conflict: await approve_model_promotion(uuid4(), ModelPromotionReviewRequest(review_note="note"), user("administrator"), service)
    assert (conflict.value.status_code, conflict.value.detail) == (409, "Model promotion state does not allow this operation")
    service.cancel_promotion = AsyncMock(side_effect=InvalidModelPromotionError("secret"))
    with pytest.raises(HTTPException) as invalid: await cancel_model_promotion(uuid4(), ModelPromotionCancelRequest(cancellation_note="note"), user(), service)
    assert invalid.value.status_code == 422


def configured_app(role_name="reviewer"):
    app, value, service, current_user = create_app(Settings()), promotion(), MagicMock(), user(role_name)
    for name in ("create_promotion", "get_promotion", "approve_promotion", "reject_promotion", "cancel_promotion"):
        setattr(service, name, AsyncMock(return_value=value))
    service.list_promotions = AsyncMock(return_value=[value])
    app.dependency_overrides[get_current_active_user] = lambda: current_user
    app.dependency_overrides[get_model_promotion_service] = lambda: service
    app.dependency_overrides[get_transactional_model_promotion_service] = lambda: service
    return app, value, service, current_user


@pytest.mark.anyio
async def test_integration_all_routes_validation_status_and_attribution() -> None:
    app, value, service, current_user = configured_app("administrator"); transport = httpx.ASGITransport(app=app)
    body = {"benchmark_comparison_id": str(value.benchmark_comparison_id), "selected_benchmark_result_id": str(value.selected_benchmark_result_id), "rationale": " evidence "}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [await client.post("/api/model-promotions", json=body), await client.get(f"/api/model-promotions/{value.id}"), await client.get("/api/model-promotions?status=pending"), await client.post(f"/api/model-promotions/{value.id}/approve", json={"review_note": "yes"}), await client.post(f"/api/model-promotions/{value.id}/reject", json={"review_note": "no"}), await client.post(f"/api/model-promotions/{value.id}/cancel", json={"cancellation_note": "stop"})]
        invalid_body = await client.post("/api/model-promotions", json={}); invalid_id = await client.get("/api/model-promotions/bad"); invalid_status = await client.get("/api/model-promotions?status=bad")
    assert [item.status_code for item in responses] == [201, 200, 200, 200, 200, 200]
    assert invalid_body.status_code == invalid_id.status_code == invalid_status.status_code == 422
    assert "total_error_cost" in responses[0].json()["selected_benchmark_result"]
    assert service.create_promotion.await_args.args[0].requested_by_user_id == current_user.id
    assert service.approve_promotion.await_args.args[0].reviewed_by_user_id == current_user.id


@pytest.mark.anyio
@pytest.mark.parametrize("role_name,create_read,review,cancel", [("reviewer", 200, 403, 200), ("administrator", 200, 200, 200), ("customer", 403, 403, 403)])
async def test_authorization_policy(role_name, create_read, review, cancel) -> None:
    app, value, _, _ = configured_app(role_name); transport = httpx.ASGITransport(app=app)
    body = {"benchmark_comparison_id": str(value.benchmark_comparison_id), "selected_benchmark_result_id": str(value.selected_benchmark_result_id), "rationale": "evidence"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        statuses = [(await client.post("/api/model-promotions", json=body)).status_code, (await client.get("/api/model-promotions")).status_code, (await client.get(f"/api/model-promotions/{value.id}")).status_code, (await client.post(f"/api/model-promotions/{value.id}/approve", json={"review_note": "yes"})).status_code, (await client.post(f"/api/model-promotions/{value.id}/reject", json={"review_note": "no"})).status_code, (await client.post(f"/api/model-promotions/{value.id}/cancel", json={"cancellation_note": "stop"})).status_code]
    assert statuses == [201 if create_read == 200 else create_read, create_read, create_read, review, review, cancel]


@pytest.mark.anyio
async def test_unauthenticated_routes_are_401() -> None:
    app = create_app(Settings()); service = MagicMock()
    app.dependency_overrides[get_model_promotion_service] = lambda: service; app.dependency_overrides[get_transactional_model_promotion_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [await client.get("/api/model-promotions"), await client.get(f"/api/model-promotions/{uuid4()}"), await client.post("/api/model-promotions", json={}), await client.post(f"/api/model-promotions/{uuid4()}/approve", json={}), await client.post(f"/api/model-promotions/{uuid4()}/reject", json={}), await client.post(f"/api/model-promotions/{uuid4()}/cancel", json={})]
    assert all(response.status_code == 401 for response in responses)
