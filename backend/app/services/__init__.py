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
from app.services.prediction import (
    ActiveModelVersionNotFoundError,
    DuplicatePredictionError,
    InvalidPredictionOutputError,
    PredictionExecutionError,
    PredictionNotAllowedError,
    PredictionNotFoundError,
    PredictionService,
    PredictionServiceError,
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
    "ActiveModelVersionNotFoundError",
    "DuplicatePredictionError",
    "InvalidPredictionOutputError",
    "PredictionExecutionError",
    "PredictionNotAllowedError",
    "PredictionNotFoundError",
    "PredictionService",
    "PredictionServiceError",
]
