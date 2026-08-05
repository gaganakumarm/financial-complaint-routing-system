"""Deployment-candidate audit-history schema and route tests."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.api.dependencies import get_current_active_user, get_deployment_candidate_service
from app.api.routes.deployment_candidates import get_latest_deployment_candidate_history, list_deployment_candidate_history
from app.core.config import Settings
from app.main import create_app
from app.models import DeploymentCandidateStatus, Role, User
from app.schemas import DeploymentCandidateStatusHistoryListResponse, DeploymentCandidateStatusHistoryResponse
from app.services import DeploymentCandidateNotFoundError

NOW = datetime.now(timezone.utc)


def history(*, previous_status=None, note=None):
    candidate_id, actor_id = uuid4(), uuid4()
    return SimpleNamespace(
        id=uuid4(), deployment_candidate_id=candidate_id,
        previous_status=previous_status, new_status=DeploymentCandidateStatus.CANDIDATE if previous_status is None else DeploymentCandidateStatus.STAGED,
        changed_by_user_id=actor_id, note=note, changed_at=NOW,
        changed_by_user=SimpleNamespace(id=actor_id, email="reviewer@example.com", full_name="Reviewer", password_hash="unsafe"),
    )


def user(role_name="reviewer"):
    value = User(id=uuid4(), role_id=uuid4(), email="user@example.com", password_hash="x", full_name="User", is_active=True, email_verified=True)
    value.role = Role(id=value.role_id, name=role_name, display_name=role_name.title(), is_active=True)
    return value


def test_history_response_schemas_are_safe_nullable_and_strict() -> None:
    value = DeploymentCandidateStatusHistoryResponse.model_validate(history())
    assert value.previous_status is None and value.note is None
    assert value.new_status is DeploymentCandidateStatus.CANDIDATE
    assert set(value.changed_by_user.model_dump()) == {"id", "email", "full_name"}
    assert "password_hash" not in value.model_dump_json()
    with pytest.raises(ValidationError):
        DeploymentCandidateStatusHistoryResponse(**value.model_dump(), sql="unsafe")
    with pytest.raises(ValidationError):
        DeploymentCandidateStatusHistoryListResponse(items=[value], offset=0, limit=100, count=1, total=1)


@pytest.mark.anyio
async def test_direct_list_delegates_pagination_preserves_order_and_empty() -> None:
    first, second, service = history(), history(previous_status=DeploymentCandidateStatus.CANDIDATE), MagicMock()
    service.list_candidate_history = AsyncMock(side_effect=[[first, second], []])
    result = await list_deployment_candidate_history(first.deployment_candidate_id, user(), service, 2, 7)
    assert [item.id for item in result.items] == [first.id, second.id]
    assert (result.offset, result.limit, result.count) == (2, 7, 2)
    service.list_candidate_history.assert_awaited_with(first.deployment_candidate_id, offset=2, limit=7)
    empty = await list_deployment_candidate_history(first.deployment_candidate_id, user(), service, 0, 100)
    assert empty.items == [] and empty.count == 0
    for method in ("create_candidate", "stage_candidate", "activate_candidate", "retire_candidate", "reject_candidate"):
        getattr(service, method).assert_not_called()


@pytest.mark.anyio
async def test_direct_latest_success_no_history_and_candidate_not_found() -> None:
    event, service = history(), MagicMock(); service.get_latest_candidate_history = AsyncMock(return_value=event)
    assert (await get_latest_deployment_candidate_history(event.deployment_candidate_id, user(), service)).id == event.id
    service.get_latest_candidate_history.return_value = None
    with pytest.raises(HTTPException) as missing_history:
        await get_latest_deployment_candidate_history(event.deployment_candidate_id, user(), service)
    assert (missing_history.value.status_code, missing_history.value.detail) == (404, "Deployment candidate history not found")
    service.get_latest_candidate_history.side_effect = DeploymentCandidateNotFoundError("secret")
    with pytest.raises(HTTPException) as missing_candidate:
        await get_latest_deployment_candidate_history(event.deployment_candidate_id, user(), service)
    assert (missing_candidate.value.status_code, missing_candidate.value.detail) == (404, "Deployment candidate not found")


def configured_app(role_name="reviewer", *, events=None, latest=...):
    application, service, actor = create_app(Settings()), MagicMock(), user(role_name)
    values = [history()] if events is None else events
    service.list_candidate_history = AsyncMock(return_value=values)
    service.get_latest_candidate_history = AsyncMock(return_value=(values[0] if latest is ... and values else latest))
    service.get_active_candidate = AsyncMock(return_value=None)
    application.dependency_overrides[get_current_active_user] = lambda: actor
    application.dependency_overrides[get_deployment_candidate_service] = lambda: service
    return application, service, values


@pytest.mark.anyio
@pytest.mark.parametrize("role_name,expected", [("reviewer", 200), ("administrator", 200), ("customer", 403)])
async def test_history_authorization_and_integration_serialization(role_name, expected) -> None:
    application, service, values = configured_app(role_name); candidate_id = values[0].deployment_candidate_id
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await client.get(f"/api/deployment-candidates/{candidate_id}/history")
        latest = await client.get(f"/api/deployment-candidates/{candidate_id}/history/latest")
    assert listed.status_code == latest.status_code == expected
    if expected == 200:
        assert listed.json()["items"][0]["previous_status"] is None
        assert set(listed.json()["items"][0]["changed_by_user"]) == {"id", "email", "full_name"}
        assert service.list_candidate_history.await_args.kwargs == {"offset": 0, "limit": 100}


@pytest.mark.anyio
async def test_empty_missing_latest_validation_route_order_and_unauthenticated() -> None:
    application, _, _ = configured_app(events=[], latest=None); candidate_id = uuid4()
    paths = list(application.openapi()["paths"])
    assert paths.index("/api/deployment-candidates/active") < paths.index("/api/deployment-candidates/{candidate_id}/history/latest") < paths.index("/api/deployment-candidates/{candidate_id}/history") < paths.index("/api/deployment-candidates/{candidate_id}")
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/deployment-candidates/active")).status_code == 404
        listed = await client.get(f"/api/deployment-candidates/{candidate_id}/history")
        latest = await client.get(f"/api/deployment-candidates/{candidate_id}/history/latest")
        invalid = [await client.get("/api/deployment-candidates/bad/history"), await client.get(f"/api/deployment-candidates/{candidate_id}/history?offset=-1"), await client.get(f"/api/deployment-candidates/{candidate_id}/history?limit=0"), await client.get(f"/api/deployment-candidates/{candidate_id}/history?limit=501")]
    assert listed.status_code == 200 and listed.json()["count"] == 0
    assert latest.status_code == 404 and latest.json()["detail"] == "Deployment candidate history not found"
    assert all(response.status_code == 422 for response in invalid)
    unauthenticated = create_app(Settings()); transport = httpx.ASGITransport(app=unauthenticated)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get(f"/api/deployment-candidates/{candidate_id}/history")).status_code == 401
        assert (await client.get(f"/api/deployment-candidates/{candidate_id}/history/latest")).status_code == 401
