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
]
