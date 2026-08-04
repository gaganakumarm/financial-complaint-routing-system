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
from app.services.complaint import (
    ComplaintAccessDeniedError,
    ComplaintNotFoundError,
    ComplaintService,
    ComplaintServiceError,
    InvalidComplaintDataError,
    InvalidComplaintRoutingError,
    InvalidComplaintStatusTransitionError,
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
    "ComplaintAccessDeniedError",
    "ComplaintNotFoundError",
    "ComplaintService",
    "ComplaintServiceError",
    "InvalidComplaintDataError",
    "InvalidComplaintRoutingError",
    "InvalidComplaintStatusTransitionError",
]
