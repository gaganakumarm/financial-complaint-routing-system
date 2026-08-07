"""Reviewer-safe complaint and reference-data API contracts."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from app.api import get_current_active_user
from app.api.dependencies import (
    get_complaint_category_repository,
    get_complaint_service,
    get_department_repository,
)
from app.core.config import Settings
from app.main import create_app
from app.models import Complaint, ComplaintCategory, ComplaintStatus, ComplaintUrgency, Department, Role, User
from app.repositories import ComplaintCategoryRepository, DepartmentRepository
from app.services import ComplaintNotFoundError, ComplaintService


def user(role_name: str) -> User:
    role_id = uuid4()
    value = User(
        id=uuid4(), role_id=role_id, email=f"{role_name}@example.com",
        password_hash="not-used", full_name=role_name.title(), is_active=True,
        email_verified=True,
    )
    value.role = Role(id=role_id, name=role_name, display_name=role_name.title(), is_active=True)
    return value


def complaint() -> Complaint:
    now = datetime.now(timezone.utc)
    return Complaint(
        id=uuid4(), reference_number="FCR-DETAIL", customer_id=uuid4(),
        title="Card dispute", description="The complete reviewer-safe description.",
        current_status=ComplaintStatus.UNDER_REVIEW,
        final_category_id=uuid4(), final_department_id=uuid4(),
        final_urgency=ComplaintUrgency.HIGH, created_at=now, updated_at=now,
    )


def configured_app(role_name: str = "reviewer"):
    application = create_app(Settings())
    service = MagicMock(spec=ComplaintService)
    category_repository = MagicMock(spec=ComplaintCategoryRepository)
    department_repository = MagicMock(spec=DepartmentRepository)
    application.dependency_overrides[get_current_active_user] = lambda: user(role_name)
    application.dependency_overrides[get_complaint_service] = lambda: service
    application.dependency_overrides[get_complaint_category_repository] = lambda: category_repository
    application.dependency_overrides[get_department_repository] = lambda: department_repository
    return application, service, category_repository, department_repository


@pytest.mark.anyio
@pytest.mark.parametrize("role_name", ["reviewer", "administrator"])
async def test_reviewer_complaint_detail_is_safe_and_role_protected(role_name: str) -> None:
    application, service, _, _ = configured_app(role_name)
    value = complaint()
    service.get_complaint = AsyncMock(return_value=value)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/reviews/complaints/{value.id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(value.id), "reference_number": value.reference_number,
        "title": value.title, "description": value.description,
        "status": "under_review", "final_category_id": str(value.final_category_id),
        "final_department_id": str(value.final_department_id),
        "final_urgency": "high", "created_at": value.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": value.updated_at.isoformat().replace("+00:00", "Z"),
    }
    assert "customer_id" not in response.json()


@pytest.mark.anyio
async def test_reviewer_complaint_detail_missing_is_generic() -> None:
    application, service, _, _ = configured_app()
    service.get_complaint = AsyncMock(side_effect=ComplaintNotFoundError("hidden"))
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/reviews/complaints/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Complaint not found"}


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/api/reviews/complaints/00000000-0000-0000-0000-000000000001", "/api/reference/complaint-categories", "/api/reference/departments"])
async def test_reviewer_read_contracts_reject_customers(path: str) -> None:
    application, _, _, _ = configured_app("customer")
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/api/reviews/complaints/00000000-0000-0000-0000-000000000001", "/api/reference/complaint-categories", "/api/reference/departments"])
async def test_reviewer_read_contracts_require_authentication(path: str) -> None:
    transport = httpx.ASGITransport(app=create_app(Settings()))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 401


@pytest.mark.anyio
@pytest.mark.parametrize("role_name", ["reviewer", "administrator"])
async def test_active_reference_data_is_semantic_and_ordered(role_name: str) -> None:
    application, _, category_repository, department_repository = configured_app(role_name)
    first_category = ComplaintCategory(id=uuid4(), code="card", display_name="Card", description="Card issues", is_active=True)
    second_category = ComplaintCategory(id=uuid4(), code="loan", display_name="Loan", description=None, is_active=True)
    first_department = Department(id=uuid4(), code="cards", display_name="Cards", description="Card team", is_active=True)
    second_department = Department(id=uuid4(), code="loans", display_name="Loans", description=None, is_active=True)
    category_repository.list_active = AsyncMock(return_value=[first_category, second_category])
    department_repository.list_active = AsyncMock(return_value=[first_department, second_department])
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        categories = await client.get("/api/reference/complaint-categories")
        departments = await client.get("/api/reference/departments")

    assert categories.status_code == departments.status_code == 200
    assert [item["name"] for item in categories.json()["items"]] == ["Card", "Loan"]
    assert [item["name"] for item in departments.json()["items"]] == ["Cards", "Loans"]
    assert all(item["active"] for item in categories.json()["items"] + departments.json()["items"])
    category_repository.list_active.assert_awaited_once_with()
    department_repository.list_active.assert_awaited_once_with()
