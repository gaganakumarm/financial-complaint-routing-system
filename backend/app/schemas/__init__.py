"""Stable public schema exports."""

from app.schemas.auth import (
    ErrorResponse,
    LoginRequest,
    RegisterRequest,
    RegistrationResponse,
    TokenResponse,
    UserResponse,
)

__all__ = [
    "ErrorResponse",
    "LoginRequest",
    "RegisterRequest",
    "RegistrationResponse",
    "TokenResponse",
    "UserResponse",
]
