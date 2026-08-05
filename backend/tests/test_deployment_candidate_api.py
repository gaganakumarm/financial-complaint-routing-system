"""Deployment-candidate schema, route, and authorization tests."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.api.dependencies import get_current_active_user, get_deployment_candidate_repository, get_deployment_candidate_service, get_transactional_deployment_candidate_repository, get_transactional_deployment_candidate_service
from app.api.routes.deployment_candidates import activate_deployment_candidate, create_deployment_candidate, get_active_deployment_candidate, list_deployment_candidates, reject_deployment_candidate, retire_deployment_candidate, stage_deployment_candidate
from app.core.config import Settings
from app.main import create_app
from app.models import DeploymentCandidateStatus, ModelPromotionStatus, Role, User
from app.schemas import DeploymentCandidateActivateRequest, DeploymentCandidateCreateRequest, DeploymentCandidateRejectRequest, DeploymentCandidateResponse, DeploymentCandidateRetireRequest, DeploymentCandidateStageRequest
from app.services import DeploymentCandidateNotFoundError, DeploymentCandidatePersistenceError, DuplicateDeploymentCandidateError, PromotionDecisionNotApprovedError, PromotionDecisionNotFoundForCandidateError
from app.services.deployment_candidate import ActiveDeploymentCandidateConflictError
from app.repositories import DeploymentCandidateRepository, DeploymentCandidateStatusHistoryRepository, ModelPromotionRepository
from app.services import DeploymentCandidateService

NOW = datetime.now(timezone.utc)


def candidate(state=DeploymentCandidateStatus.CANDIDATE):
    promotion_id, result_id, model_id, user_id = uuid4(), uuid4(), uuid4(), uuid4()
    return SimpleNamespace(
        id=uuid4(), model_promotion_decision_id=promotion_id, benchmark_result_id=result_id,
        model_version_id=model_id, status=state, registered_by_user_id=user_id,
        registered_at=NOW, staged_at=NOW if state != DeploymentCandidateStatus.CANDIDATE else None,
        activated_at=NOW if state == DeploymentCandidateStatus.ACTIVE else None,
        retired_at=NOW if state in (DeploymentCandidateStatus.RETIRED, DeploymentCandidateStatus.REJECTED) else None,
        retirement_reason="done" if state in (DeploymentCandidateStatus.RETIRED, DeploymentCandidateStatus.REJECTED) else None,
        notes=None, created_at=NOW, updated_at=NOW,
        model_promotion_decision=SimpleNamespace(id=promotion_id, benchmark_comparison_id=uuid4(), selected_benchmark_result_id=result_id, selected_model_version_id=model_id, status=ModelPromotionStatus.APPROVED, rationale="evidence", override_winner=False, requested_by_user_id=uuid4(), reviewed_by_user_id=uuid4(), requested_at=NOW, reviewed_at=NOW, created_at=NOW),
        benchmark_result=SimpleNamespace(id=result_id, benchmark_experiment_id=uuid4(), model_version_id=model_id, sample_count=10, total_error_cost=Decimal("1"), exact_match_accuracy=Decimal(".9"), failed_prediction_count=0, department_accuracy=Decimal(".9"), category_accuracy=Decimal(".8"), urgency_accuracy=Decimal(".95"), p95_inference_latency_ms=42, average_inference_latency_ms=Decimal("20"), cost_weighted_error=Decimal(".1"), created_at=NOW),
        model_version=SimpleNamespace(id=model_id, name="router", version="v1"),
        registered_by_user=SimpleNamespace(id=user_id, email="admin@example.com", full_name="Admin"),
    )


def user(role_name="administrator"):
    value = User(id=uuid4(), role_id=uuid4(), email="user@example.com", password_hash="x", full_name="User", is_active=True, email_verified=True)
    value.role = Role(id=value.role_id, name=role_name, display_name=role_name.title(), is_active=True)
    return value


def test_request_schemas_trim_forbid_extra_and_validate_lengths():
    promotion_id = uuid4()
    assert DeploymentCandidateCreateRequest(model_promotion_decision_id=promotion_id, notes=" note ").notes == "note"
    assert DeploymentCandidateCreateRequest(model_promotion_decision_id=promotion_id).notes is None
    assert DeploymentCandidateStageRequest(note=None).note is None
    assert DeploymentCandidateActivateRequest(note=" staged ").note == "staged"
    assert DeploymentCandidateRetireRequest(retirement_reason=" done ").retirement_reason == "done"
    assert DeploymentCandidateRejectRequest(rejection_reason=" no ").rejection_reason == "no"
    invalid = [
        (DeploymentCandidateCreateRequest, {"model_promotion_decision_id": promotion_id, "notes": " "}),
        (DeploymentCandidateCreateRequest, {"model_promotion_decision_id": promotion_id, "status": "active"}),
        (DeploymentCandidateStageRequest, {"note": "x" * 10001}),
        (DeploymentCandidateActivateRequest, {"note": " ", "extra": 1}),
        (DeploymentCandidateRetireRequest, {"retirement_reason": " "}),
        (DeploymentCandidateRejectRequest, {"rejection_reason": "x" * 10001}),
    ]
    for schema, payload in invalid:
        with pytest.raises(ValidationError): schema(**payload)


def test_response_serializes_nested_safe_fields_and_nullable_lifecycle():
    value = DeploymentCandidateResponse.model_validate(candidate())
    assert value.staged_at is None
    assert set(value.registered_by_user.model_dump()) == {"id", "email", "full_name"}
    assert value.benchmark_result.total_error_cost == Decimal("1")


@pytest.mark.anyio
async def test_dependency_factories_reuse_the_injected_session_and_repositories():
    session = MagicMock()
    read_repository = await get_deployment_candidate_repository(session)
    transactional_repository = await get_transactional_deployment_candidate_repository(session)
    assert isinstance(read_repository, DeploymentCandidateRepository)
    assert isinstance(transactional_repository, DeploymentCandidateRepository)
    assert read_repository.session is transactional_repository.session is session
    read_service = get_deployment_candidate_service(session)
    transactional_service = get_transactional_deployment_candidate_service(session)
    assert isinstance(read_service, DeploymentCandidateService)
    assert isinstance(transactional_service, DeploymentCandidateService)
    assert isinstance(read_service._candidates, DeploymentCandidateRepository)
    assert isinstance(transactional_service._candidates, DeploymentCandidateRepository)
    assert isinstance(read_service._promotions, ModelPromotionRepository)
    assert isinstance(transactional_service._promotions, ModelPromotionRepository)
    assert isinstance(read_service._history, DeploymentCandidateStatusHistoryRepository)
    assert isinstance(transactional_service._history, DeploymentCandidateStatusHistoryRepository)
    assert {read_service._candidates.session, read_service._promotions.session, read_service._history.session} == {session}
    assert {transactional_service._candidates.session, transactional_service._promotions.session, transactional_service._history.session} == {session}


@pytest.mark.anyio
async def test_direct_create_list_and_active_delegate():
    value, actor, service = candidate(), user(), MagicMock()
    service.create_candidate = AsyncMock(return_value=value)
    service.list_candidates = AsyncMock(return_value=[value])
    service.get_active_candidate = AsyncMock(return_value=value)
    service.stage_candidate = AsyncMock(return_value=value)
    service.activate_candidate = AsyncMock(return_value=value)
    service.retire_candidate = AsyncMock(return_value=value)
    service.reject_candidate = AsyncMock(return_value=value)
    result = await create_deployment_candidate(DeploymentCandidateCreateRequest(model_promotion_decision_id=value.model_promotion_decision_id, notes="note"), actor, service)
    assert result.id == value.id and service.create_candidate.await_args.args[0].registered_by_user_id == actor.id
    listed = await list_deployment_candidates(actor, service, DeploymentCandidateStatus.CANDIDATE, 2, 5)
    assert (listed.offset, listed.limit, listed.count) == (2, 5, 1)
    service.list_candidates.assert_awaited_once_with(status=DeploymentCandidateStatus.CANDIDATE, offset=2, limit=5)
    assert (await get_active_deployment_candidate(actor, service)).id == value.id
    await stage_deployment_candidate(value.id, DeploymentCandidateStageRequest(note="stage"), actor, service)
    await activate_deployment_candidate(value.id, DeploymentCandidateActivateRequest(note="activate"), actor, service)
    await retire_deployment_candidate(value.id, DeploymentCandidateRetireRequest(retirement_reason="retire"), actor, service)
    await reject_deployment_candidate(value.id, DeploymentCandidateRejectRequest(rejection_reason="reject"), actor, service)
    assert service.stage_candidate.await_args.args[0].staged_by_user_id == actor.id
    assert service.activate_candidate.await_args.args[0].activated_by_user_id == actor.id
    assert service.retire_candidate.await_args.args[0].retired_by_user_id == actor.id
    assert service.reject_candidate.await_args.args[0].rejected_by_user_id == actor.id


@pytest.mark.anyio
@pytest.mark.parametrize("error,code,detail", [
    (PromotionDecisionNotFoundForCandidateError("secret"), 404, "Model promotion not found"),
    (PromotionDecisionNotApprovedError("secret"), 409, "Model promotion is not approved"),
    (DuplicateDeploymentCandidateError("secret"), 409, "A deployment candidate already exists for this promotion"),
    (DeploymentCandidatePersistenceError("secret SQL"), 500, "Deployment candidate could not be persisted"),
])
async def test_create_errors_are_safe(error, code, detail):
    service = MagicMock(); service.create_candidate = AsyncMock(side_effect=error)
    with pytest.raises(HTTPException) as caught:
        await create_deployment_candidate(DeploymentCandidateCreateRequest(model_promotion_decision_id=uuid4()), user(), service)
    assert (caught.value.status_code, caught.value.detail) == (code, detail)
    assert "secret" not in str(caught.value)


@pytest.mark.anyio
async def test_active_candidate_conflict_maps_safely_in_direct_route():
    service = MagicMock(); service.activate_candidate = AsyncMock(side_effect=ActiveDeploymentCandidateConflictError("secret active details"))
    with pytest.raises(HTTPException) as caught:
        await activate_deployment_candidate(uuid4(), DeploymentCandidateActivateRequest(), user(), service)
    assert (caught.value.status_code, caught.value.detail) == (409, "Another deployment candidate is already active")
    assert "secret" not in str(caught.value)


def configured_app(role_name="administrator", active=True):
    app, value, service = create_app(Settings()), candidate(), MagicMock()
    actor = user(role_name)
    for name in ("create_candidate", "get_candidate", "stage_candidate", "activate_candidate", "retire_candidate", "reject_candidate"):
        setattr(service, name, AsyncMock(return_value=value))
    service.list_candidates = AsyncMock(return_value=[value])
    service.get_active_candidate = AsyncMock(return_value=value if active else None)
    app.dependency_overrides[get_current_active_user] = lambda: actor
    app.dependency_overrides[get_deployment_candidate_service] = lambda: service
    app.dependency_overrides[get_transactional_deployment_candidate_service] = lambda: service
    return app, value, service


@pytest.mark.anyio
@pytest.mark.parametrize("role_name,read,write", [("administrator", 200, 200), ("reviewer", 200, 403), ("customer", 403, 403)])
async def test_authorization_and_all_routes(role_name, read, write):
    app, value, _ = configured_app(role_name); transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [
            await client.get("/api/deployment-candidates"), await client.get("/api/deployment-candidates/active"), await client.get(f"/api/deployment-candidates/{value.id}"),
            await client.post("/api/deployment-candidates", json={"model_promotion_decision_id": str(value.model_promotion_decision_id)}),
            await client.post(f"/api/deployment-candidates/{value.id}/stage", json={}), await client.post(f"/api/deployment-candidates/{value.id}/activate", json={}),
            await client.post(f"/api/deployment-candidates/{value.id}/retire", json={"retirement_reason": "done"}), await client.post(f"/api/deployment-candidates/{value.id}/reject", json={"rejection_reason": "no"}),
        ]
    assert [item.status_code for item in responses[:3]] == [read, read, read]
    expected_write = 201 if role_name == "administrator" else write
    assert [item.status_code for item in responses[3:]] == [expected_write, write, write, write, write]


@pytest.mark.anyio
async def test_active_order_validation_and_unauthenticated():
    app, _, _ = configured_app(active=False); transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/deployment-candidates/active")).status_code == 404
        assert (await client.get("/api/deployment-candidates/not-a-uuid")).status_code == 422
        assert (await client.get("/api/deployment-candidates?status=bad")).status_code == 422
    unauthenticated = create_app(Settings()); transport = httpx.ASGITransport(app=unauthenticated)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/deployment-candidates")).status_code == 401


@pytest.mark.anyio
async def test_active_conflict_maps_through_integration_route():
    app, value, service = configured_app()
    service.activate_candidate.side_effect = ActiveDeploymentCandidateConflictError("database detail")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/deployment-candidates/{value.id}/activate", json={})
    assert response.status_code == 409
    assert response.json() == {"detail": "Another deployment candidate is already active"}
