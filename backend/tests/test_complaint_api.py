"""Tests for the customer complaint REST API without PostgreSQL."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from pydantic import ValidationError
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.dependencies as dependencies_module
import app.db.session as session_module
from app.api import (
    get_complaint_repository,
    get_complaint_service,
    get_transactional_complaint_repository,
    get_transactional_complaint_service,
)
from app.authz import require_customer
from app.core.config import Settings
from app.main import create_app
from app.models import Complaint, ComplaintStatus, Role, User
from app.repositories import ComplaintRepository
from app.schemas import ComplaintCreateRequest, ComplaintResponse
from app.services import (
    ComplaintAccessDeniedError,
    ComplaintNotFoundError,
    ComplaintService,
    InvalidComplaintDataError,
)


def _customer(role_name: str = "customer") -> User:
    role_id = uuid4()
    user = User(
        id=uuid4(), role_id=role_id, email="customer@example.com",
        password_hash="secret-hash", full_name="Customer", is_active=True,
        email_verified=False,
    )
    user.role = Role(
        id=role_id, name=role_name, display_name=role_name.title(), is_active=True
    )
    return user


def _complaint(customer: User | None = None) -> Complaint:
    customer = customer or _customer()
    now = datetime.now(timezone.utc)
    return Complaint(
        id=uuid4(), reference_number="FCR-ABC123", customer_id=customer.id,
        title="Card dispute", description="A disputed card transaction",
        current_status=ComplaintStatus.SUBMITTED, final_category_id=None,
        final_department_id=None, final_urgency=None, created_at=now, updated_at=now,
    )


def _app(service: MagicMock, user: User | None = None):
    application = create_app(Settings())
    application.dependency_overrides[require_customer] = lambda: user or _customer()
    application.dependency_overrides[get_complaint_service] = lambda: service
    application.dependency_overrides[get_transactional_complaint_service] = (
        lambda: service
    )
    return application


class _FakeTransaction:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.commits += 1
        else:
            self.rollbacks += 1
        return False


class _FakeSession:
    def __init__(self) -> None:
        self.transaction = _FakeTransaction()
        self.begins = 0
        self.closes = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.closes += 1
        return False

    def begin(self):
        self.begins += 1
        return self.transaction


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "", "description": "valid"},
        {"title": "x" * 201, "description": "valid"},
        {"title": "valid", "description": ""},
        {"title": "valid", "description": "x" * 10_001},
        {"title": "valid", "description": "valid", "status": "submitted"},
    ],
)
def test_create_schema_rejects_invalid_or_extra_data(payload) -> None:
    with pytest.raises(ValidationError):
        ComplaintCreateRequest.model_validate(payload)


def test_complaint_response_has_only_approved_fields() -> None:
    response = ComplaintResponse.model_validate(_complaint()).model_dump()
    assert set(response) == {
        "id", "reference_number", "customer_id", "title", "description",
        "current_status", "final_category_id", "final_department_id",
        "final_urgency", "created_at", "updated_at",
    }
    assert not {"status_history", "predictions", "reviews", "customer"} & response.keys()


@pytest.mark.anyio
async def test_dependency_construction_is_fresh_and_neutral() -> None:
    session = MagicMock(spec=AsyncSession)
    read_first = await get_complaint_repository(session)
    read_second = await get_complaint_repository(session)
    write = await get_transactional_complaint_repository(session)
    assert all(isinstance(item, ComplaintRepository) for item in (read_first, read_second, write))
    assert read_first.session is session and write.session is session
    assert read_first is not read_second
    service_first = get_complaint_service(read_first)
    service_second = get_transactional_complaint_service(write)
    assert isinstance(service_first, ComplaintService)
    assert service_first._complaint_repository is read_first
    assert service_second._complaint_repository is write
    for method in ("begin", "commit", "rollback", "flush", "refresh", "execute"):
        getattr(session, method).assert_not_called()


@pytest.mark.anyio
async def test_create_complaint_returns_safe_201_and_exact_arguments() -> None:
    customer = _customer()
    complaint = _complaint(customer)
    service = MagicMock(spec=ComplaintService)
    service.create_complaint = AsyncMock(return_value=complaint)
    transport = httpx.ASGITransport(app=_app(service, customer))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/complaints",
            json={"title": " Exact title ", "description": " Exact body "},
        )
    assert response.status_code == 201
    service.create_complaint.assert_awaited_once_with(
        customer=customer, title=" Exact title ", description=" Exact body "
    )
    assert response.json()["complaint"]["current_status"] == "submitted"
    assert response.json()["complaint"]["final_urgency"] is None
    assert "password_hash" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (InvalidComplaintDataError("hidden"), 422, "Invalid complaint data"),
        (ComplaintAccessDeniedError("hidden"), 403, "Not enough permissions"),
    ],
)
async def test_create_translates_expected_errors(error, status_code, detail) -> None:
    service = MagicMock(spec=ComplaintService)
    service.create_complaint = AsyncMock(side_effect=error)
    transport = httpx.ASGITransport(app=_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/complaints", json={"title": "title", "description": "body"}
        )
    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert "hidden" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        (_complaint(), 201),
        (InvalidComplaintDataError("hidden"), 422),
        (ComplaintAccessDeniedError("hidden"), 403),
    ],
)
async def test_create_owns_one_transaction(monkeypatch, outcome, expected_status) -> None:
    session = _FakeSession()
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)
    service = MagicMock(spec=ComplaintService)
    service.create_complaint = AsyncMock(
        side_effect=outcome if isinstance(outcome, Exception) else None,
        return_value=None if isinstance(outcome, Exception) else outcome,
    )
    constructor = MagicMock(return_value=service)
    monkeypatch.setattr(dependencies_module, "ComplaintService", constructor)
    application = create_app(Settings())
    application.dependency_overrides[require_customer] = lambda: _customer()
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/complaints", json={"title": "title", "description": "body"}
        )
    assert response.status_code == expected_status
    factory.assert_called_once_with()
    constructor.assert_called_once()
    assert session.begins == 1
    assert session.transaction.commits == (expected_status == 201)
    assert session.transaction.rollbacks == (expected_status != 201)
    assert session.closes == 1


@pytest.mark.anyio
async def test_create_unrelated_error_rolls_back_and_propagates(monkeypatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr(
        session_module, "get_session_factory", lambda: MagicMock(return_value=session)
    )
    original = RuntimeError("original failure")
    service = MagicMock(spec=ComplaintService)
    service.create_complaint = AsyncMock(side_effect=original)
    monkeypatch.setattr(dependencies_module, "ComplaintService", lambda repository: service)
    application = create_app(Settings())
    application.dependency_overrides[require_customer] = lambda: _customer()
    transport = httpx.ASGITransport(app=application)
    with pytest.raises(RuntimeError) as caught:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/api/complaints", json={"title": "title", "description": "body"}
            )
    assert caught.value is original
    assert session.transaction.commits == 0
    assert session.transaction.rollbacks == 1
    assert session.closes == 1


@pytest.mark.anyio
async def test_list_uses_customer_and_exact_pagination() -> None:
    customer = _customer()
    items = [_complaint(customer), _complaint(customer)]
    service = MagicMock(spec=ComplaintService)
    service.list_customer_complaints = AsyncMock(return_value=items)
    transport = httpx.ASGITransport(app=_app(service, customer))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/complaints?offset=3&limit=25")
    assert response.status_code == 200
    assert response.json()["count"] == 2
    service.list_customer_complaints.assert_awaited_once_with(
        customer_id=customer.id, offset=3, limit=25
    )


@pytest.mark.anyio
@pytest.mark.parametrize("query", ["offset=-1", "limit=0", "limit=501"])
async def test_list_rejects_invalid_pagination(query: str) -> None:
    service = MagicMock(spec=ComplaintService)
    transport = httpx.ASGITransport(app=_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/complaints?{query}")
    assert response.status_code == 422


@pytest.mark.anyio
async def test_detail_uses_owner_ids_and_returns_safe_response() -> None:
    customer = _customer()
    complaint = _complaint(customer)
    service = MagicMock(spec=ComplaintService)
    service.get_customer_complaint = AsyncMock(return_value=complaint)
    transport = httpx.ASGITransport(app=_app(service, customer))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/complaints/{complaint.id}")
    assert response.status_code == 200
    service.get_customer_complaint.assert_awaited_once_with(
        complaint_id=complaint.id, customer_id=customer.id
    )
    assert "status_history" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error", [ComplaintNotFoundError("secret"), ComplaintAccessDeniedError("secret")]
)
async def test_missing_and_wrong_owner_are_identical_404(error) -> None:
    service = MagicMock(spec=ComplaintService)
    service.get_customer_complaint = AsyncMock(side_effect=error)
    transport = httpx.ASGITransport(app=_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/complaints/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Complaint not found"}


def test_openapi_contract_is_safe_and_exact() -> None:
    schema = create_app(Settings()).openapi()
    assert {"/api/complaints", "/api/complaints/{complaint_id}"} <= set(schema["paths"])
    assert set(schema["paths"]["/api/complaints"]) == {"get", "post"}
    for operation in (
        schema["paths"]["/api/complaints"]["get"],
        schema["paths"]["/api/complaints"]["post"],
        schema["paths"]["/api/complaints/{complaint_id}"]["get"],
    ):
        assert operation["tags"] == ["Complaints"]
        assert operation["security"]
