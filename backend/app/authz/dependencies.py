"""Reusable role-based FastAPI authorization dependencies."""

from collections.abc import Awaitable, Callable, Collection
from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.dependencies import CurrentActiveUser
from app.authz.roles import ApplicationRole, normalize_role_name
from app.models import User


class AuthorizationError(Exception):
    """Base exception for application authorization failures."""


class MissingRoleError(AuthorizationError):
    """Raised when a user has no valid, already-loaded role."""


class InsufficientRoleError(AuthorizationError):
    """Raised by future authorization services for insufficient access."""


def get_user_role_name(user: User) -> str:
    """Resolve a canonical role from the user's loaded relationship."""
    role = user.__dict__.get("role")
    if role is None:
        raise MissingRoleError("User role is unavailable.")
    try:
        return normalize_role_name(role.name)
    except (AttributeError, ValueError):
        raise MissingRoleError("User role is unavailable.") from None


def user_has_any_role(
    user: User,
    allowed_roles: Collection[ApplicationRole | str],
) -> bool:
    """Return whether the user's canonical role is in the allowed collection."""
    if isinstance(allowed_roles, str) or not allowed_roles:
        raise ValueError("at least one allowed role is required")
    normalized_roles = {
        normalize_role_name(role_name) for role_name in allowed_roles
    }
    return get_user_role_name(user) in normalized_roles


def _forbidden_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not enough permissions",
    )


def require_roles(
    *allowed_roles: ApplicationRole | str,
) -> Callable[..., Awaitable[User]]:
    """Build a dependency that authorizes one or more canonical roles."""
    if not allowed_roles:
        raise ValueError("at least one allowed role is required")
    normalized_roles = tuple(
        dict.fromkeys(normalize_role_name(role_name) for role_name in allowed_roles)
    )

    async def role_dependency(current_user: CurrentActiveUser) -> User:
        try:
            role_name = get_user_role_name(current_user)
        except (MissingRoleError, ValueError):
            raise _forbidden_exception() from None
        if role_name not in normalized_roles:
            raise _forbidden_exception() from None
        return current_user

    return role_dependency


require_customer = require_roles(ApplicationRole.CUSTOMER)
require_reviewer = require_roles(ApplicationRole.REVIEWER)
require_administrator = require_roles(ApplicationRole.ADMINISTRATOR)
require_reviewer_or_administrator = require_roles(
    ApplicationRole.REVIEWER,
    ApplicationRole.ADMINISTRATOR,
)

CustomerUser = Annotated[User, Depends(require_customer)]
ReviewerUser = Annotated[User, Depends(require_reviewer)]
AdministratorUser = Annotated[User, Depends(require_administrator)]
ReviewerOrAdministratorUser = Annotated[
    User,
    Depends(require_reviewer_or_administrator),
]
