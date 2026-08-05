"""Tests for authentication schemas and API routes."""

from datetime import datetime, timezone
import importlib
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException
import httpx
from pydantic import ValidationError
import pytest

from app.api import (
    get_auth_service,
    get_current_active_user,
    get_transactional_auth_service,
)
from app.api.routes import auth_router
from app.api.routes.auth import login, register_user
from app.core.config import Settings
from app.db.engine import get_engine
from app.db.session import get_session_factory
from app.main import create_app
from app.models import User
from app.schemas import (
    ErrorResponse,
    LoginRequest,
    RegisterRequest,
    RegistrationResponse,
    TokenResponse,
    UserResponse,
)
from app.services import (
    AuthenticationResult,
    AuthService,
    DuplicateEmailError,
    InactiveUserError,
    InvalidCredentialsError,
)


SCHEMA_EXPORTS = {
    "DatasetExampleCreateItem", "DatasetExampleBatchCreateRequest",
    "DatasetExampleBatchCreateResponse", "DatasetExampleListResponse",
    "DatasetExampleResponse",
    "BenchmarkExperimentCreateRequest",
    "BenchmarkExperimentListResponse",
    "BenchmarkExperimentResponse",
    "BenchmarkResultListResponse",
    "BenchmarkResultResponse",
    "DatasetVersionCreateRequest",
    "DatasetVersionListResponse",
    "DatasetVersionResponse",
    "ComplaintCreateRequest",
    "ComplaintCreateResponse",
    "ComplaintListResponse",
    "ComplaintResponse",
    "PredictionListResponse",
    "PredictionResponse",
    "PredictionRunRequest",
    "PredictionRunResponse",
    "ErrorResponse",
    "LoginRequest",
    "RegisterRequest",
    "RegistrationResponse",
    "TokenResponse",
    "UserResponse",
    "ReviewActionRequest",
    "ReviewClaimResponse",
    "ReviewCorrectionRequest",
    "ReviewQueueItemResponse",
    "ReviewQueueResponse",
    "ReviewResponse",
}


def _user() -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid4(),
        role_id=uuid4(),
        email="user@example.com",
        password_hash="never-expose-this-hash",
        full_name="Example User",
        is_active=True,
        email_verified=False,
        created_at=now,
        updated_at=now,
    )


def _mock_service() -> MagicMock:
    service = MagicMock(spec=AuthService)
    service.register_user = AsyncMock()
    service.login = AsyncMock()
    service.get_current_user = AsyncMock()
    return service


def _app_with_service(service: MagicMock):
    application = create_app(Settings())
    application.dependency_overrides[get_auth_service] = lambda: service
    application.dependency_overrides[get_transactional_auth_service] = lambda: service
    return application


def test_schema_package_exports_are_exact() -> None:
    import app.schemas as schemas

    assert set(schemas.__all__) == SCHEMA_EXPORTS
    assert auth_router.prefix == "/auth"


def test_request_schemas_accept_valid_data_without_normalizing_password() -> None:
    role_id = uuid4()
    registration = RegisterRequest(
        email="Person@Example.COM",
        password="  password  ",
        full_name="Example User",
        role_id=role_id,
    )
    login_request = LoginRequest(email="Person@Example.COM", password=" password ")

    assert registration.password == "  password  "
    assert registration.role_id == role_id
    assert login_request.password == " password "


@pytest.mark.parametrize("schema", [RegisterRequest, LoginRequest])
def test_request_schemas_forbid_extra_fields(schema: type) -> None:
    values = {"email": "user@example.com", "password": "password", "extra": True}
    if schema is RegisterRequest:
        values.update(full_name="Example User", role_id=uuid4())

    with pytest.raises(ValidationError):
        schema.model_validate(values)


def test_registration_schema_rejects_malformed_uuid_and_password_limits() -> None:
    valid = {
        "email": "user@example.com",
        "full_name": "Example User",
        "role_id": uuid4(),
    }
    with pytest.raises(ValidationError):
        RegisterRequest(**valid, password="short")
    with pytest.raises(ValidationError):
        RegisterRequest(**valid, password="x" * 129)
    with pytest.raises(ValidationError):
        RegisterRequest(**{**valid, "role_id": "not-a-uuid"}, password="password")


def test_login_schema_and_token_type_validation() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="ab", password="password")
    with pytest.raises(ValidationError):
        LoginRequest(email="user@example.com", password="")
    with pytest.raises(ValidationError):
        TokenResponse(access_token="token", token_type="refresh")
    with pytest.raises(ValidationError):
        TokenResponse(access_token="   ", token_type="bearer")


def test_user_response_from_orm_excludes_password_hash() -> None:
    serialized = UserResponse.model_validate(_user()).model_dump(mode="json")

    assert "password_hash" not in serialized
    assert set(serialized) == {
        "id",
        "role_id",
        "email",
        "full_name",
        "is_active",
        "email_verified",
        "created_at",
        "updated_at",
    }


@pytest.mark.anyio
async def test_registration_returns_201_and_safe_user() -> None:
    service = _mock_service()
    user = _user()
    service.register_user.return_value = user
    application = _app_with_service(service)
    transport = httpx.ASGITransport(app=application)
    payload = {
        "email": "Person@Example.COM",
        "password": "valid-password",
        "full_name": "Example User",
        "role_id": str(user.role_id),
    }

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/auth/register", json=payload)

    assert response.status_code == 201
    assert response.json()["user"]["id"] == str(user.id)
    assert "password_hash" not in response.text
    assert "access_token" not in response.text
    service.register_user.assert_awaited_once_with(
        email=payload["email"],
        password=payload["password"],
        full_name=payload["full_name"],
        role_id=user.role_id,
    )


@pytest.mark.anyio
async def test_duplicate_registration_returns_exact_409() -> None:
    service = _mock_service()
    service.register_user.side_effect = DuplicateEmailError("internal message")
    application = _app_with_service(service)
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "user@example.com",
                "password": "valid-password",
                "full_name": "Example User",
                "role_id": str(uuid4()),
            },
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "An account with this email already exists"}


@pytest.mark.anyio
async def test_service_registration_value_error_becomes_generic_422() -> None:
    service = _mock_service()
    service.register_user.side_effect = ValueError("sensitive validation detail")
    application = _app_with_service(service)
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "user@example.com",
                "password": "valid-password",
                "full_name": "Example User",
                "role_id": str(uuid4()),
            },
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid registration data"}
    assert "sensitive validation detail" not in response.text


@pytest.mark.anyio
async def test_unrelated_registration_exception_propagates_directly() -> None:
    service = _mock_service()
    service.register_user.side_effect = RuntimeError("programming error")
    payload = RegisterRequest(
        email="user@example.com",
        password="valid-password",
        full_name="Example User",
        role_id=uuid4(),
    )

    with pytest.raises(RuntimeError, match="programming error"):
        await register_user(payload, service)


@pytest.mark.anyio
async def test_login_returns_token_only_and_delegates_exact_values() -> None:
    service = _mock_service()
    service.login.return_value = AuthenticationResult(
        user=_user(), access_token="safe-access-token"
    )
    application = _app_with_service(service)
    transport = httpx.ASGITransport(app=application)
    payload = {"email": "Person@Example.COM", "password": "valid-password"}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/auth/login", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "safe-access-token",
        "token_type": "bearer",
    }
    assert "user" not in response.json()
    assert "refresh" not in response.json()
    service.login.assert_awaited_once_with(**payload)


@pytest.mark.parametrize(
    "service_exception",
    [InvalidCredentialsError("hidden"), InactiveUserError("hidden")],
)
@pytest.mark.anyio
async def test_login_failures_return_indistinguishable_401(
    service_exception: Exception,
) -> None:
    service = _mock_service()
    service.login.side_effect = service_exception
    application = _app_with_service(service)
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "valid-password"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect email or password"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert "hidden" not in response.text


@pytest.mark.anyio
async def test_password_is_not_logged_or_echoed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _mock_service()
    service.login.side_effect = InvalidCredentialsError("hidden")
    application = _app_with_service(service)
    transport = httpx.ASGITransport(app=application)
    password = "never-echo-this-password"

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": password},
        )

    assert password not in response.text
    assert password not in caplog.text


@pytest.mark.anyio
async def test_current_user_returns_safe_profile_from_dependency() -> None:
    user = _user()
    application = create_app(Settings())
    application.dependency_overrides[get_current_active_user] = lambda: user
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    assert "password_hash" not in response.text


@pytest.mark.anyio
async def test_current_user_requires_bearer_token() -> None:
    application = create_app(Settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_current_user_authentication_failure_uses_existing_generic_401() -> None:
    service = _mock_service()
    service.get_current_user.side_effect = InvalidCredentialsError("hidden")
    application = _app_with_service(service)
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/auth/me", headers={"Authorization": "Bearer invalid-token"}
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_route_registration_is_exact_and_not_duplicated() -> None:
    first_app = create_app(Settings())
    second_app = create_app(Settings())
    expected = {
        "/health",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/me",
    }

    for application in (first_app, second_app):
        paths = list(application.openapi()["paths"])
        assert expected.issubset(paths)
        for path in expected:
            assert paths.count(path) == 1
        assert "/api/auth/refresh" not in paths
        assert "/api/auth/logout" not in paths
        assert "/api/auth/password-reset" not in paths


def test_openapi_auth_paths_schemas_and_security() -> None:
    schema = create_app(Settings()).openapi()
    paths = schema["paths"]

    assert "/api/auth/register" in paths
    assert "/api/auth/login" in paths
    assert "/api/auth/me" in paths
    assert paths["/api/auth/me"]["get"]["security"]
    assert "security" not in paths["/api/auth/login"]["post"]
    assert "security" not in paths["/api/auth/register"]["post"]
    assert schema["components"]["securitySchemes"]["OAuth2PasswordBearer"][
        "flows"
    ]["password"]["tokenUrl"] == "/api/auth/login"
    user_properties = schema["components"]["schemas"]["UserResponse"]["properties"]
    assert "password_hash" not in user_properties
    assert schema["paths"]["/api/auth/login"]["post"]["tags"] == ["Authentication"]


def test_imports_and_app_creation_do_not_create_database_resources() -> None:
    engine_cache_before = get_engine.cache_info()
    session_cache_before = get_session_factory.cache_info()

    import app.api.routes.auth as auth_routes
    import app.schemas.auth as auth_schemas

    importlib.reload(auth_routes)
    importlib.reload(auth_schemas)
    create_app(Settings())
    assert get_engine.cache_info() == engine_cache_before
    assert get_session_factory.cache_info() == session_cache_before
    assert not any(isinstance(value, AuthService) for value in vars(auth_routes).values())


@pytest.mark.anyio
async def test_routes_do_not_manage_transactions() -> None:
    service = _mock_service()
    service.register_user.return_value = _user()
    service.commit = AsyncMock()
    service.rollback = AsyncMock()
    service.begin = AsyncMock()
    application = _app_with_service(service)
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/auth/register",
            json={
                "email": "user@example.com",
                "password": "valid-password",
                "full_name": "Example User",
                "role_id": str(uuid4()),
            },
        )

    service.commit.assert_not_awaited()
    service.rollback.assert_not_awaited()
    service.begin.assert_not_awaited()
