"""Stable public API dependency exports."""

from app.api.dependencies import (
    AccessToken,
    AuthServiceDependency,
    CurrentActiveUser,
    CurrentUser,
    DatabaseSession,
    UserRepositoryDependency,
    get_auth_service,
    get_current_active_user,
    get_current_user,
    get_user_repository,
    oauth2_scheme,
)
from app.api.routes import auth_router


_AUTHORIZATION_EXPORTS = {
    "AdministratorUser",
    "CustomerUser",
    "ReviewerOrAdministratorUser",
    "ReviewerUser",
}


def __getattr__(name: str):
    if name in _AUTHORIZATION_EXPORTS:
        from app import authz

        return getattr(authz, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
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
    "AdministratorUser",
    "CustomerUser",
    "ReviewerOrAdministratorUser",
    "ReviewerUser",
]
