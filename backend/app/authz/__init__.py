"""Stable public authorization API."""

from app.authz.dependencies import (
    AdministratorUser,
    AuthorizationError,
    CustomerUser,
    InsufficientRoleError,
    MissingRoleError,
    ReviewerOrAdministratorUser,
    ReviewerUser,
    get_user_role_name,
    require_administrator,
    require_customer,
    require_reviewer,
    require_reviewer_or_administrator,
    require_roles,
    user_has_any_role,
)
from app.authz.roles import ApplicationRole, normalize_role_name

__all__ = [
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
]
