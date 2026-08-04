"""JWT access-token creation and validation."""

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings


class InvalidAccessTokenError(ValueError):
    """Raised when an access token fails validation."""


class ExpiredAccessTokenError(InvalidAccessTokenError):
    """Raised when an otherwise parseable access token has expired."""


def _normalize_required(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank")
    return normalized


def _utc_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(timezone.utc)


def create_access_token(
    subject: str,
    *,
    expires_delta: timedelta | None = None,
    now: datetime | None = None,
) -> str:
    """Create a signed HS256 access token with required claims."""
    normalized_subject = _normalize_required(subject, "subject")
    settings = get_settings()
    issued_at = _utc_now(now)
    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    if lifetime <= timedelta(0):
        raise ValueError("access-token expiry must be greater than zero")
    expires_at = issued_at + lifetime
    return jwt.encode(
        {
            "sub": normalized_subject,
            "iat": issued_at,
            "exp": expires_at,
            "type": "access",
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(
    token: str,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Validate and decode an HS256 access token."""
    normalized_token = _normalize_required(token, "token")
    if now is not None:
        _utc_now(now)
    settings = get_settings()
    try:
        payload = jwt.decode(
            normalized_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "iat", "exp", "type"]},
        )
    except jwt.ExpiredSignatureError:
        raise ExpiredAccessTokenError("access token has expired") from None
    except jwt.PyJWTError:
        raise InvalidAccessTokenError("access token is invalid") from None

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise InvalidAccessTokenError("access token is invalid")
    if payload.get("type") != "access":
        raise InvalidAccessTokenError("access token is invalid")
    return dict(payload)
