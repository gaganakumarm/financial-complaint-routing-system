"""Tests for FastAPI authentication dependency wiring."""

import importlib
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.security import OAuth2PasswordBearer
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.api as api
from app.api import (
    AccessToken,
    AuthServiceDependency,
    BenchmarkComparisonRepositoryDependency,
    BenchmarkComparisonServiceDependency,
    CurrentActiveUser,
    CurrentUser,
    DatabaseSession,
    TransactionalAuthServiceDependency,
    TransactionalBenchmarkComparisonRepositoryDependency,
    TransactionalBenchmarkComparisonServiceDependency,
    TransactionalDatabaseSession,
    TransactionalUserRepositoryDependency,
    UserRepositoryDependency,
    get_auth_service,
    get_benchmark_comparison_repository,
    get_benchmark_comparison_service,
    get_current_active_user,
    get_current_user,
    get_transactional_auth_service,
    get_transactional_benchmark_comparison_repository,
    get_transactional_benchmark_comparison_service,
    get_transactional_session,
    get_transactional_user_repository,
    get_user_repository,
    oauth2_scheme,
)
from app.db.engine import get_engine
from app.db.session import get_session_factory
from app.main import app as production_app
from app.models import User
from app.repositories import BenchmarkComparisonRepository, BenchmarkResultRepository, UserRepository
from app.services import (
    AuthService,
    BenchmarkComparisonService,
    InactiveUserError,
    InvalidCredentialsError,
    UserNotFoundError,
)


EXPECTED_EXPORTS = {
    "BenchmarkComparisonRepositoryDependency", "BenchmarkComparisonServiceDependency",
    "TransactionalBenchmarkComparisonRepositoryDependency", "TransactionalBenchmarkComparisonServiceDependency",
    "get_benchmark_comparison_repository", "get_transactional_benchmark_comparison_repository",
    "get_benchmark_comparison_service", "get_transactional_benchmark_comparison_service",
    "benchmark_comparisons_router",
    "DatasetExampleRepositoryDependency", "TransactionalDatasetExampleRepositoryDependency",
    "DatasetExampleServiceDependency", "TransactionalDatasetExampleServiceDependency",
    "get_dataset_example_repository", "get_transactional_dataset_example_repository",
    "get_dataset_example_service", "get_transactional_dataset_example_service",
    "dataset_examples_router",
    "AdministratorUser",
    "AccessToken",
    "AuthServiceDependency",
    "BenchmarkExperimentRepositoryDependency",
    "BenchmarkPredictorFactoryDependency",
    "BenchmarkResultRepositoryDependency",
    "BenchmarkServiceDependency",
    "ComplaintRepositoryDependency",
    "ComplaintPredictorDependency",
    "ComplaintServiceDependency",
    "CurrentActiveUser",
    "CurrentUser",
    "CustomerUser",
    "DatabaseSession",
    "DatasetVersionRepositoryDependency",
    "DatasetServiceDependency",
    "ModelVersionRepositoryDependency",
    "PredictionRepositoryDependency",
    "PredictionServiceDependency",
    "ReviewRepositoryDependency",
    "ReviewServiceDependency",
    "TransactionalAuthServiceDependency",
    "TransactionalBenchmarkExperimentRepositoryDependency",
    "TransactionalBenchmarkResultRepositoryDependency",
    "TransactionalBenchmarkServiceDependency",
    "TransactionalComplaintRepositoryDependency",
    "TransactionalComplaintServiceDependency",
    "TransactionalDatabaseSession",
    "TransactionalDatasetVersionRepositoryDependency",
    "TransactionalDatasetServiceDependency",
    "TransactionalModelVersionRepositoryDependency",
    "TransactionalPredictionRepositoryDependency",
    "TransactionalPredictionServiceDependency",
    "TransactionalReviewRepositoryDependency",
    "TransactionalReviewServiceDependency",
    "TransactionalUserRepositoryDependency",
    "UserRepositoryDependency",
    "ReviewerOrAdministratorUser",
    "ReviewerUser",
    "get_auth_service",
    "get_benchmark_experiment_repository",
    "get_benchmark_predictor_factory",
    "get_benchmark_result_repository",
    "get_benchmark_service",
    "get_complaint_repository",
    "get_complaint_predictor",
    "get_complaint_service",
    "get_current_active_user",
    "get_current_user",
    "get_dataset_version_repository",
    "get_dataset_service",
    "get_prediction_repository",
    "get_prediction_service",
    "get_model_version_repository",
    "get_review_repository",
    "get_review_service",
    "get_transactional_auth_service",
    "get_transactional_benchmark_experiment_repository",
    "get_transactional_benchmark_result_repository",
    "get_transactional_benchmark_service",
    "get_transactional_complaint_repository",
    "get_transactional_complaint_service",
    "get_transactional_dataset_version_repository",
    "get_transactional_dataset_service",
    "get_transactional_model_version_repository",
    "get_transactional_prediction_repository",
    "get_transactional_prediction_service",
    "get_transactional_review_repository",
    "get_transactional_review_service",
    "get_transactional_session",
    "get_transactional_user_repository",
    "get_user_repository",
    "oauth2_scheme",
    "auth_router",
    "benchmarks_router",
    "complaints_router",
    "datasets_router",
    "predictions_router",
    "reviews_router",
}


def _user() -> User:
    return User(
        id=uuid4(),
        role_id=uuid4(),
        email="user@example.com",
        password_hash="not-used",
        full_name="Example User",
        is_active=True,
        email_verified=False,
    )


def test_approved_imports_and_exact_exports() -> None:
    assert {
        AccessToken,
        AuthServiceDependency,
        CurrentActiveUser,
        CurrentUser,
        DatabaseSession,
        TransactionalAuthServiceDependency,
        TransactionalDatabaseSession,
        TransactionalUserRepositoryDependency,
        UserRepositoryDependency,
    }
    assert callable(get_auth_service)
    assert callable(get_current_active_user)
    assert callable(get_current_user)
    assert callable(get_transactional_auth_service)
    assert callable(get_transactional_session)
    assert callable(get_transactional_user_repository)
    assert callable(get_user_repository)
    assert set(api.__all__) == EXPECTED_EXPORTS


def test_oauth2_scheme_configuration() -> None:
    assert isinstance(oauth2_scheme, OAuth2PasswordBearer)
    assert oauth2_scheme.model.flows.password.tokenUrl == "/api/auth/login"
    assert oauth2_scheme.model.flows.password.scopes == {}
    assert oauth2_scheme.auto_error is True


@pytest.mark.anyio
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Basic credentials"}])
async def test_oauth2_scheme_rejects_missing_or_wrong_authentication_scheme(
    headers: dict[str, str],
) -> None:
    temporary_app = FastAPI()

    @temporary_app.get("/token")
    async def token_route(token: AccessToken) -> dict[str, str]:
        return {"token": token}

    transport = httpx.ASGITransport(app=temporary_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/token", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_oauth2_scheme_returns_only_bearer_token() -> None:
    temporary_app = FastAPI()

    @temporary_app.get("/token")
    async def token_route(token: AccessToken) -> dict[str, str]:
        return {"token": token}

    transport = httpx.ASGITransport(app=temporary_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/token", headers={"Authorization": "Bearer exact-token-value"}
        )

    assert response.status_code == 200
    assert response.json() == {"token": "exact-token-value"}


@pytest.mark.anyio
async def test_user_repository_dependency_uses_exact_session_and_is_fresh() -> None:
    session = MagicMock(spec=AsyncSession)

    first = await get_user_repository(session)
    second = await get_user_repository(session)

    assert isinstance(first, UserRepository)
    assert first.session is session
    assert second.session is session
    assert second is not first
    for method in ("commit", "rollback", "begin", "flush", "refresh", "execute"):
        getattr(session, method).assert_not_called()


def test_auth_service_dependency_uses_exact_repository_and_is_fresh() -> None:
    repository = MagicMock(spec=UserRepository)

    first = get_auth_service(repository)
    second = get_auth_service(repository)

    assert isinstance(first, AuthService)
    assert first._user_repository is repository
    assert second._user_repository is repository
    assert second is not first
    assert repository.mock_calls == []


@pytest.mark.anyio
async def test_benchmark_comparison_dependencies_share_the_injected_session() -> None:
    session = MagicMock(spec=AsyncSession)
    read_repository = await get_benchmark_comparison_repository(session)
    transactional_repository = await get_transactional_benchmark_comparison_repository(session)
    assert isinstance(read_repository, BenchmarkComparisonRepository)
    assert read_repository.session is session and transactional_repository.session is session
    result_repository = BenchmarkResultRepository(session)
    read_service = get_benchmark_comparison_service(read_repository, result_repository)
    transactional_service = get_transactional_benchmark_comparison_service(transactional_repository, result_repository)
    assert isinstance(read_service, BenchmarkComparisonService)
    assert read_service._comparisons is read_repository and read_service._results is result_repository
    assert transactional_service._comparisons is transactional_repository and transactional_service._results is result_repository
    for method in ("commit", "rollback", "begin", "flush", "refresh", "execute"):
        getattr(session, method).assert_not_called()


@pytest.mark.anyio
async def test_current_user_delegates_exact_token_and_returns_same_user() -> None:
    user = _user()
    auth_service = MagicMock(spec=AuthService)
    auth_service.get_current_user = AsyncMock(return_value=user)

    result = await get_current_user("exact-token", auth_service)

    assert result is user
    auth_service.get_current_user.assert_awaited_once_with("exact-token")


@pytest.mark.parametrize(
    "service_exception",
    [
        InvalidCredentialsError("sensitive service detail"),
        InactiveUserError("sensitive service detail"),
        UserNotFoundError("sensitive service detail"),
    ],
)
@pytest.mark.anyio
async def test_authentication_failures_become_generic_401(
    service_exception: Exception,
) -> None:
    auth_service = MagicMock(spec=AuthService)
    auth_service.get_current_user = AsyncMock(side_effect=service_exception)

    with pytest.raises(HTTPException) as caught:
        await get_current_user("secret-token", auth_service)

    assert caught.value.status_code == 401
    assert caught.value.detail == "Could not validate credentials"
    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}
    assert "sensitive service detail" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.anyio
async def test_each_authentication_failure_gets_new_http_exception() -> None:
    auth_service = MagicMock(spec=AuthService)
    auth_service.get_current_user = AsyncMock(
        side_effect=InvalidCredentialsError("hidden")
    )
    caught: list[HTTPException] = []

    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            await get_current_user("token", auth_service)
        caught.append(error.value)

    assert caught[0] is not caught[1]


@pytest.mark.anyio
async def test_unrelated_service_error_propagates() -> None:
    auth_service = MagicMock(spec=AuthService)
    auth_service.get_current_user = AsyncMock(side_effect=RuntimeError("bug"))

    with pytest.raises(RuntimeError, match="bug"):
        await get_current_user("token", auth_service)


@pytest.mark.anyio
async def test_current_active_user_returns_same_unmodified_user() -> None:
    user = _user()
    original_state = dict(user.__dict__)

    result = await get_current_active_user(user)

    assert result is user
    assert user.__dict__ == original_state


def _temporary_current_user_app(auth_service: MagicMock) -> FastAPI:
    temporary_app = FastAPI()
    temporary_app.dependency_overrides[get_auth_service] = lambda: auth_service

    @temporary_app.get("/test/current-user")
    async def current_user_route(user: CurrentUser) -> dict[str, str]:
        return {"user_id": str(user.id)}

    return temporary_app


@pytest.mark.anyio
async def test_temporary_route_resolves_service_user_from_bearer_token() -> None:
    user = _user()
    auth_service = MagicMock(spec=AuthService)
    auth_service.get_current_user = AsyncMock(return_value=user)
    temporary_app = _temporary_current_user_app(auth_service)
    transport = httpx.ASGITransport(app=temporary_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/test/current-user", headers={"Authorization": "Bearer service-token"}
        )

    assert response.status_code == 200
    assert response.json() == {"user_id": str(user.id)}
    auth_service.get_current_user.assert_awaited_once_with("service-token")


@pytest.mark.anyio
@pytest.mark.parametrize("authorization", [None, "Basic credentials"])
async def test_temporary_route_rejects_invalid_bearer_header(
    authorization: str | None,
) -> None:
    auth_service = MagicMock(spec=AuthService)
    temporary_app = _temporary_current_user_app(auth_service)
    transport = httpx.ASGITransport(app=temporary_app)
    headers = {} if authorization is None else {"Authorization": authorization}

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test/current-user", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_temporary_route_converts_service_failure_to_generic_401() -> None:
    auth_service = MagicMock(spec=AuthService)
    auth_service.get_current_user = AsyncMock(
        side_effect=InvalidCredentialsError("do not expose")
    )
    temporary_app = _temporary_current_user_app(auth_service)
    transport = httpx.ASGITransport(app=temporary_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/test/current-user", headers={"Authorization": "Bearer bad-token"}
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_import_has_no_resource_construction_or_production_routes() -> None:
    engine_cache_before = get_engine.cache_info()
    session_cache_before = get_session_factory.cache_info()
    routes_before = set(production_app.openapi()["paths"])

    import app.api.dependencies as dependencies

    importlib.reload(dependencies)
    assert get_engine.cache_info() == engine_cache_before
    assert get_session_factory.cache_info() == session_cache_before
    assert set(production_app.openapi()["paths"]) == routes_before
    assert not any(
        isinstance(value, (UserRepository, AuthService))
        for value in vars(dependencies).values()
    )
