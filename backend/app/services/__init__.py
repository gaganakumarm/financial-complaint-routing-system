"""Stable public service API."""

from app.services.auth import (
    AuthenticationError,
    AuthenticationResult,
    AuthService,
    DuplicateEmailError,
    InactiveUserError,
    InvalidCredentialsError,
    UserNotFoundError,
    create_access_token_for_user,
)

__all__ = [
    "AuthenticationError",
    "AuthenticationResult",
    "AuthService",
    "DuplicateEmailError",
    "InactiveUserError",
    "InvalidCredentialsError",
    "UserNotFoundError",
    "create_access_token_for_user",
]
