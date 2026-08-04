"""Tests for role-based authorization infrastructure."""

import importlib
import inspect
from typing import Annotated, get_args, get_origin
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.params import Depends as DependsParameter
import httpx
import pytest

import app.api as api
import app.authz as authz
from app.api import get_current_active_user
from app.authz import (
    AdministratorUser,
    ApplicationRole,
    AuthorizationError,
    CustomerUser,
    InsufficientRoleError,
    MissingRoleError,
    ReviewerOrAdministratorUser,
    ReviewerUser,
    get_user_role_name,
    normalize_role_name,
    require_administrator,
    require_customer,
    require_reviewer,
    require_reviewer_or_administrator,
    require_roles,
    user_has_any_role,
)
from app.db.engine import get_engine
from app.db.session import get_session_factory
from app.main import app as production_app
from app.models import Role, User
from app.repositories import UserRepository
from app.services import AuthService


AUTHZ_EXPORTS = {
    "AdministratorUser",
    "ApplicationRole",
    "AuthorizationError",
    "CustomerUser",
    "InsufficientRoleError",
    "MissingRoleError",
    "ReviewerOrAdministratorUser",
    "ReviewerUser",
    "get_user_role_name",
    "normalize_role_name",
    "require_administrator",
    "require_customer",
    "require_reviewer",
    "require_reviewer_or_administrator",
    "require_roles",
    "user_has_any_role",
}


def _user_with_role(role_name: str | None) -> User:
    user = User(
        id=uuid4(),
        role_id=uuid4(),
        email="user@example.com",
        password_hash="unused",
        full_name="Example User",
        is_active=True,
        email_verified=False,
    )
    if role_name is not None:
        role = Role(id=user.role_id, name=role_name, display_name="Role", is_active=True)
        user.role = role
    return user


def test_application_roles_have_exact_members_and_values() -> None:
    assert list(ApplicationRole) == [
        ApplicationRole.CUSTOMER,
        ApplicationRole.REVIEWER,
        ApplicationRole.ADMINISTRATOR,
    ]
    assert [role.value for role in ApplicationRole] == [
        "customer",
        "reviewer",
        "administrator",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("customer", "customer"),
        (" reviewer ", "reviewer"),
        ("ADMINISTRATOR", "administrator"),
        (ApplicationRole.CUSTOMER, "customer"),
    ],
)
def test_normalize_role_name_accepts_canonical_roles(value: str, expected: str) -> None:
    assert normalize_role_name(value) == expected


@pytest.mark.parametrize(
    "value", ["", "   ", "unknown", "admin", "superuser", "staff", "analyst"]
)
def test_normalize_role_name_rejects_invalid_roles(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_role_name(value)


@pytest.mark.parametrize("role_name", ["customer", "reviewer", "administrator"])
def test_user_role_resolution_from_loaded_relationship(role_name: str) -> None:
    assert get_user_role_name(_user_with_role(role_name.upper())) == role_name


@pytest.mark.parametrize("role_name", [None, "", "unknown"])
def test_missing_or_invalid_user_role_raises_missing_role(
    role_name: str | None,
) -> None:
    with pytest.raises(MissingRoleError):
        get_user_role_name(_user_with_role(role_name))


def test_user_role_resolution_performs_no_repository_access() -> None:
    repository = MagicMock(spec=UserRepository)

    assert get_user_role_name(_user_with_role("customer")) == "customer"
    assert repository.mock_calls == []


def test_pure_role_check_supports_enums_strings_multiple_and_duplicates() -> None:
    reviewer = _user_with_role("reviewer")

    assert user_has_any_role(reviewer, [ApplicationRole.REVIEWER]) is True
    assert user_has_any_role(reviewer, ["customer"]) is False
    assert user_has_any_role(
        reviewer, ["customer", ApplicationRole.REVIEWER]
    ) is True
    assert user_has_any_role(reviewer, ["reviewer", "reviewer"]) is True


def test_pure_role_check_rejects_empty_or_invalid_allowed_roles() -> None:
    user = _user_with_role("customer")
    with pytest.raises(ValueError):
        user_has_any_role(user, [])
    with pytest.raises(ValueError):
        user_has_any_role(user, ["admin"])


def test_require_roles_validates_at_factory_creation() -> None:
    with pytest.raises(ValueError):
        require_roles()
    with pytest.raises(ValueError):
        require_roles("admin")
    assert inspect.iscoroutinefunction(require_roles("customer"))


@pytest.mark.anyio
async def test_required_role_returns_exact_authorized_user() -> None:
    user = _user_with_role("customer")
    dependency = require_roles(" customer ", ApplicationRole.CUSTOMER)

    assert await dependency(user) is user


@pytest.mark.anyio
async def test_unauthorized_role_raises_generic_403() -> None:
    dependency = require_roles(ApplicationRole.ADMINISTRATOR)

    with pytest.raises(HTTPException) as caught:
        await dependency(_user_with_role("reviewer"))

    assert caught.value.status_code == 403
    assert caught.value.detail == "Not enough permissions"
    assert not caught.value.headers
    assert "reviewer" not in str(caught.value)


@pytest.mark.anyio
async def test_missing_role_becomes_generic_403() -> None:
    with pytest.raises(HTTPException) as caught:
        await require_customer(_user_with_role(None))

    assert caught.value.status_code == 403
    assert caught.value.detail == "Not enough permissions"
    assert caught.value.__cause__ is None


@pytest.mark.anyio
async def test_each_forbidden_failure_creates_new_exception() -> None:
    failures: list[HTTPException] = []
    for _ in range(2):
        with pytest.raises(HTTPException) as caught:
            await require_customer(_user_with_role("reviewer"))
        failures.append(caught.value)

    assert failures[0] is not failures[1]


@pytest.mark.anyio
async def test_unrelated_role_resolution_error_propagates() -> None:
    dependency = require_roles("customer")
    with patch(
        "app.authz.dependencies.get_user_role_name",
        side_effect=RuntimeError("programming error"),
    ):
        with pytest.raises(RuntimeError, match="programming error"):
            await dependency(_user_with_role("customer"))


@pytest.mark.parametrize(
    ("dependency", "accepted_roles"),
    [
        (require_customer, {"customer"}),
        (require_reviewer, {"reviewer"}),
        (require_administrator, {"administrator"}),
        (require_reviewer_or_administrator, {"reviewer", "administrator"}),
    ],
)
@pytest.mark.anyio
async def test_named_dependencies_have_no_implicit_hierarchy(
    dependency, accepted_roles: set[str]
) -> None:
    for role_name in ("customer", "reviewer", "administrator"):
        user = _user_with_role(role_name)
        if role_name in accepted_roles:
            assert await dependency(user) is user
        else:
            with pytest.raises(HTTPException):
                await dependency(user)


@pytest.mark.parametrize(
    ("alias", "dependency"),
    [
        (CustomerUser, require_customer),
        (ReviewerUser, require_reviewer),
        (AdministratorUser, require_administrator),
        (ReviewerOrAdministratorUser, require_reviewer_or_administrator),
    ],
)
def test_typed_alias_references_expected_dependency(alias, dependency) -> None:
    assert get_origin(alias) is Annotated
    metadata = get_args(alias)[1:]
    assert len(metadata) == 1
    assert isinstance(metadata[0], DependsParameter)
    assert metadata[0].dependency is dependency


def _authorization_app(user: User) -> FastAPI:
    temporary_app = FastAPI()
    temporary_app.dependency_overrides[get_current_active_user] = lambda: user

    @temporary_app.get("/customer")
    async def customer_route(current_user: CustomerUser) -> dict[str, str]:
        return {"user_id": str(current_user.id)}

    @temporary_app.get("/review")
    async def review_route(
        current_user: ReviewerOrAdministratorUser,
    ) -> dict[str, str]:
        return {"user_id": str(current_user.id)}

    @temporary_app.get("/admin")
    async def admin_route(current_user: AdministratorUser) -> dict[str, str]:
        return {"user_id": str(current_user.id)}

    return temporary_app


@pytest.mark.parametrize(
    ("role_name", "path", "expected_status"),
    [
        ("customer", "/customer", 200),
        ("customer", "/review", 403),
        ("reviewer", "/review", 200),
        ("reviewer", "/admin", 403),
        ("administrator", "/review", 200),
        ("administrator", "/admin", 200),
        ("administrator", "/customer", 403),
    ],
)
@pytest.mark.anyio
async def test_fastapi_role_dependency_integration(
    role_name: str, path: str, expected_status: int
) -> None:
    temporary_app = _authorization_app(_user_with_role(role_name))
    transport = httpx.ASGITransport(app=temporary_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == expected_status
    if expected_status == 403:
        assert response.json() == {"detail": "Not enough permissions"}


@pytest.mark.anyio
async def test_fastapi_missing_role_returns_403() -> None:
    temporary_app = _authorization_app(_user_with_role(None))
    transport = httpx.ASGITransport(app=temporary_app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/customer")

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}


@pytest.mark.anyio
async def test_unauthenticated_request_remains_401_without_override() -> None:
    temporary_app = FastAPI()

    @temporary_app.get("/customer")
    async def customer_route(current_user: CustomerUser) -> dict[str, str]:
        return {"user_id": str(current_user.id)}

    transport = httpx.ASGITransport(app=temporary_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/customer")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_exact_package_and_api_exports() -> None:
    assert set(authz.__all__) == AUTHZ_EXPORTS
    prior_api_exports = {
        "AccessToken",
        "AuthServiceDependency",
        "CurrentActiveUser",
        "CurrentUser",
        "DatabaseSession",
        "UserRepositoryDependency",
        "get_auth_service",
        "get_current_active_user",
        "get_current_user",
        "get_user_repository",
        "oauth2_scheme",
        "auth_router",
    }
    assert set(api.__all__) == prior_api_exports | {
        "AdministratorUser",
        "CustomerUser",
        "ReviewerOrAdministratorUser",
        "ReviewerUser",
    }


def test_authorization_import_has_no_side_effects_or_production_routes() -> None:
    engine_cache_before = get_engine.cache_info()
    session_cache_before = get_session_factory.cache_info()
    routes_before = set(production_app.openapi()["paths"])

    import app.authz.dependencies as dependencies

    importlib.reload(dependencies)
    assert get_engine.cache_info() == engine_cache_before
    assert get_session_factory.cache_info() == session_cache_before
    assert set(production_app.openapi()["paths"]) == routes_before == {
        "/health",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/me",
    }
    assert not any(
        isinstance(value, (UserRepository, AuthService))
        for value in vars(dependencies).values()
    )
