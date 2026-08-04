"""Stable public API dependency exports."""

from app.api.dependencies import (
    AccessToken,
    AuthServiceDependency,
    ComplaintRepositoryDependency,
    ComplaintServiceDependency,
    CurrentActiveUser,
    CurrentUser,
    DatabaseSession,
    TransactionalAuthServiceDependency,
    TransactionalComplaintRepositoryDependency,
    TransactionalComplaintServiceDependency,
    TransactionalDatabaseSession,
    TransactionalUserRepositoryDependency,
    UserRepositoryDependency,
    get_auth_service,
    get_complaint_repository,
    get_complaint_service,
    get_current_active_user,
    get_current_user,
    get_transactional_auth_service,
    get_transactional_complaint_repository,
    get_transactional_complaint_service,
    get_transactional_user_repository,
    get_user_repository,
    oauth2_scheme,
)
from app.db.session import get_transactional_session
from app.api.routes import auth_router, complaints_router


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
    "ComplaintRepositoryDependency",
    "ComplaintServiceDependency",
    "CurrentActiveUser",
    "CurrentUser",
    "DatabaseSession",
    "TransactionalAuthServiceDependency",
    "TransactionalComplaintRepositoryDependency",
    "TransactionalComplaintServiceDependency",
    "TransactionalDatabaseSession",
    "TransactionalUserRepositoryDependency",
    "UserRepositoryDependency",
    "get_auth_service",
    "get_complaint_repository",
    "get_complaint_service",
    "get_current_active_user",
    "get_current_user",
    "get_transactional_auth_service",
    "get_transactional_complaint_repository",
    "get_transactional_complaint_service",
    "get_transactional_session",
    "get_transactional_user_repository",
    "get_user_repository",
    "oauth2_scheme",
    "auth_router",
    "complaints_router",
    "AdministratorUser",
    "CustomerUser",
    "ReviewerOrAdministratorUser",
    "ReviewerUser",
]
