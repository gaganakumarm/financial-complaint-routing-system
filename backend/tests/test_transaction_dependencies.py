"""Tests for request-scoped transaction ownership without a database."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as session_module
import app.api.dependencies as dependencies_module
from app.api import (
    TransactionalDatabaseSession,
    get_auth_service,
    get_current_active_user,
    get_current_user,
    get_transactional_auth_service,
    get_transactional_user_repository,
)
from app.db.session import get_db_session, get_transactional_session
from app.core.config import Settings
from app.main import create_app
from app.models import Role, User
from app.repositories import UserRepository
from app.services import AuthService, DuplicateEmailError


class FakeTransaction:
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


class FakeSession:
    def __init__(self) -> None:
        self.transaction = FakeTransaction()
        self.begins = 0
        self.closes = 0
        self.events: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.closes += 1
        return False

    def begin(self):
        self.begins += 1
        return self.transaction


def _install_factory(monkeypatch: pytest.MonkeyPatch, session: FakeSession) -> MagicMock:
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(session_module, "get_session_factory", lambda: factory)
    return factory


@pytest.mark.anyio
async def test_read_session_remains_nontransactional(monkeypatch) -> None:
    session = FakeSession()
    factory = _install_factory(monkeypatch, session)

    dependency = get_db_session()
    assert await anext(dependency) is session
    await dependency.aclose()

    factory.assert_called_once_with()
    assert session.begins == 0
    assert session.transaction.commits == 0
    assert session.transaction.rollbacks == 0
    assert session.closes == 1


@pytest.mark.anyio
async def test_transaction_success_commits_once_after_work(monkeypatch) -> None:
    session = FakeSession()
    factory = _install_factory(monkeypatch, session)
    dependency = get_transactional_session()

    assert await anext(dependency) is session
    assert session.transaction.commits == 0
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)

    factory.assert_called_once_with()
    assert session.begins == 1
    assert session.transaction.commits == 1
    assert session.transaction.rollbacks == 0
    assert session.closes == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [RuntimeError("original failure"), HTTPException(409, "same detail")],
)
async def test_transaction_failure_rolls_back_and_preserves_error(
    monkeypatch, error: Exception
) -> None:
    session = FakeSession()
    _install_factory(monkeypatch, session)
    dependency = get_transactional_session()
    await anext(dependency)

    with pytest.raises(type(error)) as caught:
        await dependency.athrow(error)

    assert caught.value is error
    assert session.transaction.commits == 0
    assert session.transaction.rollbacks == 1
    assert session.closes == 1


@pytest.mark.anyio
async def test_transactional_repository_is_fresh_and_transaction_neutral() -> None:
    session = MagicMock(spec=AsyncSession)
    first = await get_transactional_user_repository(session)
    second = await get_transactional_user_repository(session)

    assert isinstance(first, UserRepository)
    assert first.session is session and second.session is session
    assert first is not second
    for method in ("begin", "commit", "rollback"):
        getattr(session, method).assert_not_called()


def test_transactional_service_is_fresh_and_transaction_neutral() -> None:
    repository = MagicMock(spec=UserRepository)
    first = get_transactional_auth_service(repository)
    second = get_transactional_auth_service(repository)

    assert isinstance(first, AuthService)
    assert first._user_repository is repository
    assert second._user_repository is repository
    assert first is not second
    assert repository.mock_calls == []


def _direct_dependencies(route) -> set[object]:
    return {dependency.call for dependency in route.dependant.dependencies}


def test_auth_route_dependency_graph_uses_one_appropriate_service() -> None:
    from app.api.routes import auth_router

    routes = {
        route.path: route
        for route in auth_router.routes
        if hasattr(route, "path") and hasattr(route, "dependant")
    }
    assert get_transactional_auth_service in _direct_dependencies(
        routes["/auth/register"]
    )
    assert get_auth_service in _direct_dependencies(routes["/auth/login"])
    me_calls = _direct_dependencies(routes["/auth/me"])
    assert me_calls == {get_current_active_user}
    assert get_current_user not in me_calls


@pytest.mark.anyio
async def test_fastapi_transaction_boundary_commits_and_rolls_back(monkeypatch) -> None:
    session = FakeSession()
    _install_factory(monkeypatch, session)
    app = FastAPI()

    @app.get("/ok")
    async def ok(db: TransactionalDatabaseSession):
        return {"same_session": db is session}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ok")

    assert response.status_code == 200
    assert response.json() == {"same_session": True}
    assert session.transaction.commits == 1
    assert session.transaction.rollbacks == 0
    assert session.closes == 1


@pytest.mark.anyio
async def test_fastapi_http_exception_is_unchanged_after_rollback(monkeypatch) -> None:
    session = FakeSession()
    _install_factory(monkeypatch, session)
    app = FastAPI()

    @app.get("/failure")
    async def failure(db: TransactionalDatabaseSession):
        raise HTTPException(409, "unchanged detail")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/failure")

    assert response.status_code == 409
    assert response.json() == {"detail": "unchanged detail"}
    assert session.transaction.commits == 0
    assert session.transaction.rollbacks == 1
    assert session.closes == 1


def _registration_user() -> User:
    now = datetime.now(timezone.utc)
    role_id = uuid4()
    return User(
        id=uuid4(),
        role_id=role_id,
        email="user@example.com",
        password_hash="not-returned",
        full_name="Example User",
        is_active=True,
        email_verified=False,
        created_at=now,
        updated_at=now,
        role=Role(
            id=role_id,
            name="customer",
            display_name="Customer",
            is_active=True,
        ),
    )


def _registration_payload() -> dict[str, str]:
    return {
        "email": "user@example.com",
        "password": "valid-password",
        "full_name": "Example User",
        "role_id": str(uuid4()),
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("outcome", "expected_status", "expected_detail"),
    [
        (_registration_user(), 201, None),
        (
            DuplicateEmailError("duplicate"),
            409,
            "An account with this email already exists",
        ),
        (ValueError("invalid"), 422, "Invalid registration data"),
    ],
)
async def test_registration_response_drives_transaction_outcome(
    monkeypatch, outcome, expected_status: int, expected_detail: str | None
) -> None:
    session = FakeSession()
    _install_factory(monkeypatch, session)
    service = MagicMock(spec=AuthService)
    if isinstance(outcome, Exception):
        service.register_user = AsyncMock(side_effect=outcome)
    else:
        service.register_user = AsyncMock(return_value=outcome)
    monkeypatch.setattr(dependencies_module, "AuthService", lambda repository: service)
    application = create_app(Settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/auth/register", json=_registration_payload())

    assert response.status_code == expected_status
    if expected_detail is not None:
        assert response.json() == {"detail": expected_detail}
    assert session.begins == 1
    assert session.transaction.commits == (expected_status == 201)
    assert session.transaction.rollbacks == (expected_status != 201)
    assert session.closes == 1


@pytest.mark.anyio
async def test_registration_unrelated_error_rolls_back_unchanged(monkeypatch) -> None:
    session = FakeSession()
    _install_factory(monkeypatch, session)
    original = RuntimeError("original server failure")
    service = MagicMock(spec=AuthService)
    service.register_user = AsyncMock(side_effect=original)
    monkeypatch.setattr(dependencies_module, "AuthService", lambda repository: service)
    application = create_app(Settings())
    transport = httpx.ASGITransport(app=application)

    with pytest.raises(RuntimeError) as caught:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post("/api/auth/register", json=_registration_payload())

    assert caught.value is original
    assert session.transaction.commits == 0
    assert session.transaction.rollbacks == 1
    assert session.closes == 1
